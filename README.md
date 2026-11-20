# herdr-layout

Layout + tooling untuk dua produk Herdr yang **terpisah**: CLI/TUI (`herdr`) dan app desktop (`herdr-app` + `herdr-core`). Keduanya tidak berbagi konfigurasi.

## Instal

Butuh Herdr ≥ 0.9.0 dan Python ≥ 3.11 (memakai `tomllib`).

```sh
herdr plugin install <owner>/herdr-layout    # dari GitHub
herdr plugin link ~/path/ke/herdr-layout     # dari checkout lokal
herdr plugin log list --plugin herdr-layout  # melihat hasil apply
```

Bind aksinya di `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "prefix+shift+a"
type = "plugin_action"
command = "herdr-layout.apply"

[[keys.command]]
key = "prefix+shift+r"
type = "plugin_action"
command = "herdr-layout.replace"
```

Dokumentasi Herdr yang dipakai sebagai rujukan ada di `docs/`.


| | CLI / TUI | Desktop app |
| --- | --- | --- |
| binary | `herdr` 0.9.5 | `herdr-app` 0.1.16, core `hc` |
| home | `~/.config/herdr` | `~/.config/herdr-app` |
| config | `config.toml` | `settings.json`, `keys.json` |
| ekstensi | `herdr-plugin.toml` + `herdr plugin link` | `mods/<name>/main.js` |
| layout | tidak ada (scripted) | `layouts/<name>.json` + `preview` svg |

## CLI / TUI

```
apply.py             workspace + split + agent dari .herdr/layout.toml (idempoten; --replace buat ulang)
pick.py              popup picker (curses) untuk memilih project
herdr-plugin.toml    actions: apply, replace, dry-run, pick; event worktree.created
layout.example.toml  skema: [workspace] (label/cwd/focus/env) + [[pane]] direction/from/ratio/tab/wait/env/command/agent
```

```sh
python3 apply.py --selftest          # offline
python3 test_apply.py                # end-to-end lawan stub herdr
python3 apply.py --dry-run           # cetak argv
python3 apply.py --replace           # tutup workspace berlabel sama, buat ulang (--force bila ada agent jalan)
herdr plugin log list --plugin herdr-layout
```

Tiap `[[pane]]` boleh punya `tab = "run"` (pane pindah ke tab itu; tiap tab punya root sendiri, `from`/`ratio` relatif ke tab) dan `wait = 0.4` (jeda detik sebelum `command`/`agent`). `env` di `[workspace]` hanya untuk root shell.

Keybind (`~/.config/herdr/config.toml`): `prefix+shift+a` apply, `prefix+shift+r` replace, `prefix+shift+p` pick.

## Desktop app

- `~/.config/herdr-app/layouts/dev-layout.json` — pane sebagai kartu, rail `changes`/`files`/`agent` 340 px, status bar.
- `~/.config/herdr-app/mods/nm-logo/` — logo "NM" 44 px di kiri atas sidebar (warna ikut theme: `accent` + `accent_foreground`).
- `~/.config/herdr-app/mods/nm-nav/` — bar navigasi 38 px di paling atas; tiap tombol = satu entri `["Label", ikon, aksi]` di `GROUPS`/`RIGHT`. Aksi: `{panel:"files"}` isi panel kanan, `{mod:"nama"}` buka overlay, `{toggle:"panel"}` sembunyikan/tampilkan, `null` = command palette. Ikon dipinjam dari `mods/kanban/*.svg` dan `mods/workspace-chrome/*.svg` (tanpa aset baru). Tombol `Files`/`Changes`/`Agent` mengisi stack panel kanan dan menyala saat panel itu aktif. Tooltip tiap tombol menampilkan pintasan yang dibaca dari `keys.json` (termasuk binding per-layout), jadi ikut berubah kalau keybind diganti. Tombol palette di kanan memakai keycap asli (`⌘⇧P`). Node `sidebar` dan `panel` bisa disembunyikan: tombol `Sidebar`/`Panel` di kanan atau `cmd-shift-b` / `cmd-shift-a`.
- `~/.config/herdr-app/mods/spaces/` — daftar space: warna stabil, worktree di bawah repo, branch/ahead/behind, `●n` file belum di-commit, dot status agent, rollup `!n`/`●n` bila >1 agent, nama duplikat diberi folder induk + `#n`, filter lewat ikon kaca pembesar. Kanan-klik = Pin to top/Rename/Worktree/Close; drag = urut ulang.
- `~/.config/herdr-app/mods/agents/` — daftar agent: sort `Priority`/`Grouped by space` (ikon jam), pin saat hover, lipat sub-agent, filter lewat ikon kaca pembesar.
- `~/.config/herdr-app/mods/workspace-status/` — status bar: `N agents · M needs you`; klik bagian `needs you` untuk fokus ke agent yang blocked.
- `~/.config/herdr-app/mods/agent-progress/` — panel Agent: agent yang sedang jalan (status, activity, folder, branch, sub-agent), file yang berubah dan diff-nya. Dua tab: `Summary` (status + file/diff) dan `Feed` (event tool/file realtime dari session store agent: OpenCode `opencode.db`, Claude Code `~/.claude/projects`, Codex `~/.codex/sessions`; poll 2 detik, fallback ke status/title Herdr bila tidak ada adapter). Mengikuti agent yang difokuskan; kalau fokus pindah ke terminal biasa, agent terakhir yang tetap tampil. Perubahan yang dihitung = semua yang belum di-commit di repo agent. Tombol `Agent` di bar atas menampilkannya; klik lagi saat panel Agent aktif untuk menyembunyikan rail. `cmd-shift-a`/tombol `Panel` menyembunyikan seluruh rail.
- `~/.config/herdr-app/layouts/dev-layout.svg` — preview di Settings.
- Isi tab (vim / zsh / hermes) dibuat sekali via `herdr-app do`; layout tidak bisa membuat terminal.

```sh
herdr-app do layout.switch --name dev-layout   # atau ctrl+shift+l
herdr-app status                               # layout + errors
herdr-app shot out.png
```

`app-space.py` membuat tab dev (dari `.herdr/layout.toml` yang sama; tanpa layout: editor | shell / agent) di folder mana pun tanpa merebut fokus. `ratio` diabaikan, `agent` dicari di PATH:

```sh
python3 app-space.py --folder ~/code/repo --agent /absolute/path/to/hermes
python3 app-space.py --dry-run
```

## Gotcha

1. App tidak membaca `~/.config/herdr/config.toml` — keybind/plugin CLI tidak muncul di window.
2. `themes/*.json` strict: tanpa `name`/`author`, warna harus `#rrggbb` (alpha ditolak).
3. `pane.split --argv` tidak lewat login shell: pakai path absolut (`/absolute/path/to/hermes`), bukan `claude`. `app-space.py` membungkus `command` dengan `$SHELL -lc`, jadi nama pendek tetap jalan di sana.
4. Layout tidak punya `ratio`; ukuran pane digeser manual dan tersimpan di `layouts/.state/`.
5. `apply.py` exit 1 senyap bila tidak ada `.herdr/layout.toml` — pesan ada di plugin log dan native notification. Pencarian berhenti di root git (tidak naik ke folder induk di luar repo); worktree baru memakai layout main worktree.
6. Membuat mod baru (`mods/<name>/`) membuat app menyisipkan blok 320 px berisi mod itu di **root** layout personal yang sedang tampil. Root `dev-layout` harus hanya berisi `workspace`; kalau ada node hex random di root, hapus.
7. Klik di UI (drag/tutup panel) disimpan di `layouts/.state/<layout>.json` dan **mengalahkan** file layout. Kembalikan dengan `herdr-app do layout.show --id panel` / `layout.resize`.
8. `--replace` menolak menutup workspace yang agent-nya `working`/`blocked` (dibaca dari `pane list`; payload tak dikenal = dianggap kosong). Pakai `--force` kalau memang mau dibunuh.

skipped: restore otomatis layout CLI saat server start, mod desktop custom, layout bertingkat per-worktree.
