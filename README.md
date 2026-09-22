# gtd

A local-first CLI that syncs items from multiple inboxes (Google Tasks, Spotify playlists, org files, ...) into one destination.

## Install

```sh
uv sync
```

## Usage

```sh
gtd auth tasks       # authorize an inbox (tasks, spotify)
gtd sync              # move open items from source inboxes into the destination
```

Configure inboxes in `~/.config/gtd/config.yaml` (override with `--config`). See `config.yaml` for an example.
