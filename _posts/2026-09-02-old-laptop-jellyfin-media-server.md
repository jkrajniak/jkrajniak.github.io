---
layout: post
title: "An old laptop as a LAN-only Jellyfin server"
date: 2026-09-02
description: "Turn a spare laptop into a home media box: Ubuntu Server, no Docker, git as the source of truth, and Home Assistant deciding when a download may use the full Wi-Fi."
tags:
  - jellyfin
  - homelab
  - linux
  - home-assistant
  - self-hosting
---

I had a spare Lenovo IdeaPad and a USB disk. I wanted movies and series on the phone, on the same Wi-Fi, with no port-forward and no cloud account. The result is a small Ubuntu Server box I call **Medioteka**: [Jellyfin](https://jellyfin.org/) plays files I already have. A git repo rebuilds the laptop over SSH. If something is downloading, a cron job asks [Home Assistant](https://www.home-assistant.io/) whether anyone is home before the client may use the full Wi-Fi.

This post is the shape of that setup, not a paste of every install command. I do not click around on the IdeaPad.

### Constraints that decided the design

- **LAN only.** Web UIs listen on the home subnet. There is no Tailscale and no router hole.
- **No Docker.** Bind-mounting `/dev/dri` for transcode is fine in a container, but I did not want image pull as the rebuild story. Apt, tarballs, and systemd are enough.
- **The lid stays closed.** `HandleLidSwitch=ignore` and sleep targets are masked. The machine stays on; it stays plugged in.
- **Media is on USB, config is on the internal disk.** The OS disk is never the library. The USB is mounted by UUID, with `nofail` and `x-systemd.automount`, so a missing cable does not block boot and a replug remounts on the next access.
- **Git is the source of truth.** Another computer is the admin workstation. Host files live in the repo (`nginx`, `systemd`, `cron.d`, bootstrap scripts). Apply with `rsync` and a script that is safe to run twice.

The library is files on that USB disk: copies I already have, rips of discs I own, purchases. Jellyfin does not fetch films from the internet.

### The stack

The player is enough to watch. The other apps are optional filing. The box works if they are off.

| Job | Software | How you open it |
|---|---|---|
| Watch | Jellyfin | `http://jellyfin.local/` or `:8096` in the Android app |
| What is this box? | nginx landing page | `http://media.local/` |
| Tidy names (optional) | Radarr, Sonarr | `http://radarr.local/`, `http://sonarr.local/` |
| Shared catalog login (optional) | Prowlarr | `http://prowlarr.local/` |
| Download client (optional) | qBittorrent-nox | `http://qbittorrent.local/` |

Everything except Home Assistant runs on the IdeaPad. Clients stay on the LAN. The admin laptop never serves media; it only pushes git and SSH.

![Component diagram: LAN clients, nginx and apps on the IdeaPad, USB media, Home Assistant as a read-only occupancy source](/assets/images/posts/old-laptop-jellyfin-media-server/components.svg)

*Component layout (by author). Jellyfin plus the USB disk is the player. The rest is optional.*

Jellyfin watches `/mnt/media/movies` and `/mnt/media/tv` and scans on a timer, so a new file shows up without a manual refresh.

Hardware transcode is VAAPI on the UHD 620 (`/dev/dri/renderD128`). Phones often cannot direct-play E-AC3; the server has to transcode.

### Optional filing, not a store

Radarr and Sonarr can rename files and keep season folders tidy. They can also talk to a download client. I treat that as housekeeping for files I am already allowed to have, not as a shop.

If you use a download client at all, attach only catalogs you have a right to search: a tracker you belong to, a paid index you subscribe to, public domain, your own machine. [Prowlarr](https://prowlarr.com/) is just one login page for those catalogs so Radarr and Sonarr do not each store the same URL.

An **indexer** in that optional path is a catalog (name, year, quality, a link). It is not the player and not a licence. This post does not name catalogs and does not explain how to find one. With none configured, Radarr and Sonarr still look up artwork. Nothing downloads. That is the correct idle state.

| Piece | Job |
|---|---|
| USB folder | Where the files actually are |
| Jellyfin | Play what is on disk |
| Radarr / Sonarr (optional) | Match names, folders, a quality profile |
| Prowlarr (optional) | One place to attach catalogs you already use |
| Download client (optional) | Fetch a file you are allowed to fetch |

If you never add Prowlarr, you still have a media server. Copy files onto the disk.

### One hostname per app

Ubuntu Server does not ship Avahi. Without it, `something.local` does not resolve. After `avahi-daemon` is on, pick a hostname such as `media.local`. Extra names are extra A records for the same IPv4: `jellyfin.local`, `radarr.local`, and so on.

DNS names a host, not a port. nginx on port 80 looks at `Host` and proxies to the app ports. The Android Jellyfin app is happier with `http://jellyfin.local:8096` (or the laptop's IPv4 and port 8096) than with a name that only works on port 80. Jellyfin's published server URI for the LAN subnet stays on that IPv4 so HLS playlists do not break on mDNS.

The landing page is the runbook: Play Store links for Jellyfin (phone and Android TV) and the server URL to type in the app.

### Use cases

Three paths matter in daily use: watch something, put a file on the disk, and keep a video call usable if a download is running.

#### 1. Watch on the phone

A guest (or I, on a new phone) should not need SSH.

1. Open `http://media.local/` on the same Wi-Fi.
2. Install the official Jellyfin app from Play Store (or Jellyfin for Android TV).
3. Add the server as `http://jellyfin.local:8096`. If the name does not resolve, use the laptop's IPv4 and port 8096.
4. Sign in and pick a title that is already in the library.

![Watch flow: landing page, Play Store, add server, play or transcode](/assets/images/posts/old-laptop-jellyfin-media-server/usecase-watch.svg)

*Watch path (by author).*

The app talks to Jellyfin on 8096, not to nginx. That avoids HLS playlists that break when the published URL is only a `.local` name on port 80. If the file is H.264 plus E-AC3, the phone often cannot direct-play; VAAPI on the UHD 620 transcodes on the laptop.

#### 2. Put a title on the disk

This is a file job, not something I do in the Jellyfin app.

1. Copy the files you already have onto `/mnt/media/movies` or `/mnt/media/tv` (`rsync`, a USB stick, whatever you use).
2. Keep a simple layout: one movie folder, or `Show/Season N/`.
3. Optional: let Radarr or Sonarr rename and move, if you already use those apps to file a library.
4. Jellyfin watches the folders and scans every 15 minutes. The title shows up in the phone app.

![Add-title flow: copy files to the USB disk, optional rename, Jellyfin scan](/assets/images/posts/old-laptop-jellyfin-media-server/usecase-add.svg)

*Library path (by author). The player starts from files on disk.*

#### 3. Keep a video call usable if something is downloading

The IdeaPad is on Wi-Fi 5. A large transfer and a video call share the same access point. The rule is: cap when someone is home during the day; go fast when the house is empty, it is night, or I flip a Home Assistant switch.

I use that rule for [qBittorrent](https://www.qbittorrent.org/) when it is running. Upload stays tiny so the radio has room for the call. The same idea applies to any bulk copy on that Wi-Fi.

![Bandwidth decision: full-speed switch, night, or empty house → unlimited; otherwise 1 MiB/s](/assets/images/posts/old-laptop-jellyfin-media-server/usecase-bandwidth.svg)

*Bandwidth path (by author).*

### How the throttle is implemented

The WAN link can be hundreds of megabits. The bottleneck is the laptop radio. Daytime download is **1 MiB/s** (~8 Mbps). Night uses the client's own alternative rate limits in a window you set on the host (I use the small hours): unlimited download, upload still tiny.

Home Assistant already has an occupancy binary sensor (the same one that can turn lights off when the house is empty). A dashboard toggle can force full speed even if someone is home. The media box does not write to Home Assistant. Every five minutes, cron runs a small Python script:

1. `GET /api/states/binary_sensor.occupancy` (and the full-speed helper).
2. If the switch is on, or it is night, or the house has been empty for a few minutes, lift the global download limit.
3. If someone is home during the day, set 1 MiB/s.
4. If Home Assistant does not answer, keep the cap.

A short empty window matches the debounce already used for lights, so a flaky presence reading does not open the throttle during a call. Cron every five minutes also means that after you walk in, full speed can continue for up to one more poll. That is the tradeoff for not hammering the API.

The job is a line in `/etc/cron.d`, not a systemd timer:

```
MAILTO=""
*/5 * * * * media /usr/bin/python3 /usr/local/sbin/presence_limits.py
```

The script reads a root-owned env file for the Home Assistant token and the download-client password. Tokens stay off git.

qBittorrent's WebAPI talks about limits in **bytes per second**, while the config file stores **KiB/s**. Setting `dl_limit` to `1024` does not give you 1 MiB/s; you want `1 * 1024 * 1024`. I learned that the loud way.

### Firewall, sleep, and power cuts

UFW allows the home subnet to SSH, HTTP, Jellyfin (including discovery UDP), and the other local app ports. Incoming default is deny.

Closing the lid must not suspend. Logind ignores the lid on battery and on AC. `sleep.target` and friends are masked. Check with `/proc/acpi/button/lid/*/state` if you do not trust it: `closed` and `uptime` still climbing is the success test.

Set the host timezone to the one you actually live in. A scheduler left on `Etc/UTC` will open the night window at the wrong local hour.

A short blackout is already handled: the laptop battery is the UPS. After a long outage that empties the battery, this IdeaPad stays off. The consumer BIOS has no "power on after AC loss" (that is a desktop or ThinkPad option). I press the power button. Do not flash a modified BIOS to invent that switch.

### What I would change

Put the laptop on Ethernet. Presence-based limits exist because the server shares Wi-Fi with laptops that need a video call. A cable would make the daytime cap a courtesy, not a requirement.

The rest I would keep: one git repo, native packages, names on `.local`, a landing page that tells a guest how to install the app, and Home Assistant as a read-only occupancy signal.

If you already run Home Assistant, the occupancy half is the interesting part. The rest is a boring, rebuildable media box, which is the point.
