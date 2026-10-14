# Security

## Reporting a problem

If you find a security problem in Hanami or its website, please report it
privately: on GitHub, open the **Security** tab of this repository and choose
**Report a vulnerability**. Please don't open a public issue for it.

Fixes go out as a new release, and the report is published once people can
update.

## What Hanami does on its own

- It starts a program only when you pick it in the panel. Ports and
  rewrites it finds by itself are marked new until you keep or hide them.
- It goes online only to GitHub, at most once a day, to read the newest
  version number and the list of known ports (`online = false` turns both
  off). It never downloads or installs a program by itself.
- It reads the files of Steam, Heroic, Lutris, Epic and GOG to find games,
  and never changes them. It writes only its own settings, state and cache
  files.

## Checking a download

Every release lists a `SHA256SUMS` file and a signed record of how each file
was built. To check a download with the GitHub command line tool:

```
gh attestation verify hanami-x86_64.AppImage -R sjdsjadjajdjsa/hanami
```

or compare its checksum by hand:

```
sha256sum -c SHA256SUMS --ignore-missing
```
