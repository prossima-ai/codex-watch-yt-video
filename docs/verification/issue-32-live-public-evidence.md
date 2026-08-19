# Issue #32 live public-media evidence

## Result

The approved English automatic-VTT caption action completed against the named
public source. The L-01 run outcome is `PASS` with `partial` transcript
coverage: direct-caption evidence satisfies L-01, while the separately approved
focused visual rerun is `BLOCKED` because YouTube returned HTTP 403 before frame
extraction. Its visual provenance is `none`; no frame, visual observation, or
visual claim was created.

## Captions-first run

- Source host: `www.youtube.com`; video ID: `5Qu2SkSQeBU`; not live; duration
  observed as 1835 seconds.
- The user approved source metadata/caption inventory, chose `en` automatic
  VTT, and separately approved the one-time direct native-caption action.
- The retrieval was bounded to 4 MiB. The retained VTT is 364,442 bytes with
  SHA-256 `65c283417771339ff055e6cab8ac58e75d65f27cb2ce0963eb53155039858569`.
- Runtime evidence reported zero redirects, 1,998 normalized segments, and
  automatic-caption provenance. Transcript coverage is partial: 1.51–1835.0
  seconds are available and 0.0–1.51 seconds are unavailable.
- No media download completed during the captions-first run. No provider path,
  audio upload, or credential read was selected or observed.

## Focused visual rerun

The user separately approved a 469–479-second run, capped at ten frames. The
source metadata probe succeeded, then the approved media request received HTTP
403. The retained media artifact is zero bytes (SHA-256 of the empty file), no
frames exist, and no visual conclusion is valid. This is a source limitation,
not a successful visual inspection.

## Boundaries

The machine-readable card is
`docs/verification/issue-32-evidence.json`. It intentionally excludes the
opaque approval receipt, direct-caption URL, raw VTT, credentials, and cookies.
The temporary runtime workspaces remain retained. This run does not establish
Desktop package discovery, provider behavior, live cleanup, or release
readiness.
