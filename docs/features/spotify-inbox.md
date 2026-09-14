# Spotify inbox

## Goal

Add a `spotify` inbox kind so that tracks saved to a Spotify playlist can be
synced into GTD like any other inbox (`gtd sync`), following the pattern
already established by `tasks.TasksInbox` and `org.OrgInbox`.

Typical use case: the user has a Spotify playlist ("Inbox") they add tracks
to while listening around, and wants each track to show up as a TODO item in
their destination inbox, with the playlist cleared afterwards.

## Config shape

New `gtd.spotify.Config`, following `gtd.tasks.Config`:

```python
class Config(BaseModel):
    kind: Literal["spotify"] = "spotify"
    playlist: str          # playlist name, resolved like TasksInbox._find_tasklist_id
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, playlist: str) -> Self: ...  # CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN

    def client(self) -> Any: ...  # builds an authenticated Spotify client
```

Example `config.yaml` entry:

```yaml
inbox:
  - config:
      kind: spotify
      playlist: Inbox
      client_id: ...
      client_secret: ...
      refresh_token: ...
```

`gtd.config.InboxConfig.config` becomes
`tasks.Config | org.Config | spotify.Config` (discriminated union on `kind`),
and `build_inbox` gets a matching `case spotify.Config()` branch.

## Auth

Spotify uses OAuth 2.0 Authorization Code flow (access tokens expire after
1h; a refresh token is used to mint new ones per-request, same shape as the
Google Tasks setup).

- Add the `spotipy` dependency (thin, actively maintained wrapper around the
  Web API; handles refreshing the access token from a refresh token via
  `SpotifyOAuth`).
- Required scopes: `playlist-read-private` (read playlist contents) and
  `playlist-modify-private playlist-modify-public` (needed for `clear()` to
  remove tracks — a playlist can be either).

### `gtd auth <inbox>` subcommand

Registration/token-minting moves into the CLI instead of living in
standalone scripts. This replaces `scripts/get_tasks_token.py` (deleted)
and avoids adding a second one-off script for Spotify.

- New subcommand `gtd auth {tasks,spotify}` — a positional `inbox` argument
  selects which inbox's interactive registration flow to run.
- Each inbox module that needs interactive registration exposes an
  `authorize() -> None`:
  - `gtd.tasks.authorize()` — the logic currently in
    `scripts/get_tasks_token.py`, moved as-is: prompt for client id/secret,
    run `InstalledAppFlow.from_client_config(...).run_local_server(port=0)`,
    print the refresh token.
  - `gtd.spotify.authorize()` — same shape using
    `spotipy.oauth2.SpotifyOAuth`: prompt for client id/secret, run the
    local-redirect flow, print the refresh token.
  - `org` has no auth flow (it's a local file) and isn't registered.
- `src/gtd/__main__.py` adds:
  - `AUTH_FLOWS: dict[str, Callable[[], None]]` = `{"tasks": tasks.authorize,
    "spotify": spotify.authorize}`.
  - `run_auth(ns: Namespace) -> None` dispatching on `ns.inbox` (wrapped to
    match the existing `async def run_*` convention, even though the flow
    itself is synchronous/blocking).
  - `set_auth_parser(parser)` adding the positional `inbox` argument with
    `choices=sorted(AUTH_FLOWS)`, wired into `create_parser()` alongside
    `sync` as a new `auth` subparser.
- `scripts/get_tasks_token.py` is deleted, and the `scripts/` directory goes
  away entirely (nothing else uses it).
- Usage: `gtd auth tasks` / `gtd auth spotify` prints the refresh token to
  stdout for the user to paste into `config.yaml` or export as
  `REFRESH_TOKEN`.

## `SpotifyInbox` (`src/gtd/spotify.py`)

Mirrors `TasksInbox`:

- `_find_playlist_id()` — page through
  `client.current_user_playlists()`, match by `playlist.name == self._playlist`,
  raise `LookupError` on zero or multiple matches (same contract as
  `TasksInbox._find_tasklist_id`).
- `get_items(status=None)` — page through
  `client.playlist_items(playlist_id)`, map each track to:
  - `title`: `f"{track['name']} — {', '.join(a['name'] for a in track['artists'])}"`
  - `description`: `track['external_urls']['spotify']` (link back to the track)
  - `status`: `Status.TODO` (Spotify has no concept of task status — every
    track in the playlist counts as open)
  Skip items whose track is `None` (removed/unavailable tracks) or that are
  local files (no stable ID to act on later).
  Filter by `status` the same way the other inboxes do.
- `add(items)` — **not supported**; raises `NotImplementedError`. This inbox
  is a source only: turning an arbitrary GTD `Item` into "a Spotify track"
  isn't a well defined operation (would require a search + a best-effort
  match). Flagged as an open question below in case the user wants it
  anyway.
- `clear()` — remove all currently-present tracks from the playlist (batch
  `client.playlist_remove_all_occurrences_of_items`, chunked to the API's
  100-items-per-request limit).
- `__str__` — `f"SpotifyInbox({self._playlist})"`, matching the others.

## Wiring

- `src/gtd/config.py`: extend the `InboxConfig.config` union and
  `build_inbox` match statement.
- `src/gtd/__main__.py`: add the `auth` subparser/dispatch described above.
- `pyproject.toml`:
  - add `spotipy` to `[project.dependencies]` (not `dev`, since `gtd auth
    spotify` is a normal CLI command any user runs).
  - move `google-auth-oauthlib` from the `dev` dependency group to
    `[project.dependencies]` for the same reason — `gtd auth tasks` now
    needs it outside of development.
- `scripts/get_tasks_token.py`: delete; logic moves into
  `gtd.tasks.authorize()`.
- `tests/test_spotify.py`: integration test mirroring `tests/test_tasks.py`
  (`@pytest.mark.integration`, `Config.from_env`, asserts items round-trip),
  gated the same way behind `--integration`.

## Spotify Developer Policy notes

Checked against Spotify's current Developer Terms/Policy and the February
2026 Web API changes (see sources below). A personal, single-user CLI
syncing your own playlist into your own task manager is within intended
use — nothing here blocks the plan, but a few things affect implementation:

- **Personal/non-commercial use is explicitly allowed.** The policy's
  restrictions target commercial use and building databases/mirrors of
  Spotify's catalog, not a to-do-list line per track.
- **Use `/playlists/{id}/items`, not `/playlists/{id}/tracks`.** The Feb
  2026 migration renamed the playlist tracks endpoint; `spotipy` calls
  should target the current endpoint.
- **Development Mode now requires the app owner to have Spotify Premium**,
  or the integration stops working — note this as a prerequisite alongside
  the client id/secret in setup docs.
- **Development Mode caps: 5 authorized users per Client ID, 1 Client ID
  per developer.** No impact on a personal tool, but means this app
  registration shouldn't later be reused for anything multi-user.
- **Never use synced data to train an ML/AI model** — explicit, unambiguous
  prohibition in the policy. Not a risk for this feature, but worth keeping
  in mind if the synced items ever feed something else downstream.

Sources: [Spotify Developer Terms](https://developer.spotify.com/terms),
[Spotify Developer Policy](https://developer.spotify.com/policy/),
[Update on Developer Access and Platform Security](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security),
[Web API Changelog - February 2026](https://developer.spotify.com/documentation/web-api/references/changes/february-2026),
[February 2026 Web API Dev Mode Changes - Migration Guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).

## Open questions

1. **`add()` semantics** — confirm "not supported" is acceptable, vs.
   resolving items to tracks via search (ambiguous, needs a matching
   strategy) or appending them as literal unplayable placeholder entries
   (not really meaningful for Spotify).
2. **Playlist identity** — resolving by name (like tasklists) means renames
   silently break the config; consider allowing a playlist ID/URI instead of
   or in addition to a name.
3. **Pagination limits** — Spotify caps playlist item pages at 100; need to
   loop on `next` like the existing paginated Google APIs already do
   implicitly via the client library.
4. **Rate limiting** — spotipy raises on 429; decide whether `gtd sync`
   should retry/backoff or just surface the error like today's other
   inboxes do.
