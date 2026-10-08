# Changelog

## 1.1.1 (2026-10-08)

### Fixed
- The album and playlist ⋯ (more actions) button: its icon was light on the accent fill and hard
  to see. It now uses the same dark-on-accent colour as Play and Shuffle.

## 1.1.0 (2026-10-08)

### Added
- Light mode (Snow Storm). The theme follows Cider's Light/Dark appearance setting.
- Light and dark share the same layout and rules; only colours differ.
- Eight optional accents, enabled one at a time on top of the base: Glacier, Deep Frost,
  Arctic Teal, Aurora Red, Aurora Orange, Aurora Yellow, Aurora Green, Aurora Purple.
- Optional Aurora layer, combinable with any accent: yellow lyric sweep, purple marker for the
  playing item, yellow for favourites, red for remove, green for Library, orange for Radio and Concerts.
- Shared material for floating surfaces: player, queue bar, profile pill, notifications panel,
  popovers and menus.
- Rubik for titles and lyrics, Inter for the interface.
- Fonts bundled with the theme; no external font requests.
- Hover and open transitions for rows, buttons, cards and menus.
- Reduced-motion setting honoured, including Cider's own toggle.
- Slim floating scrollbars.
- Contrast check at build time for every colour role on every surface, in both appearances and
  with every accent (WCAG AA).

### Fixed
- Black areas when Cider's window transparency is enabled.
- White text on a white background in light-mode dialogs.
- Remove-from-queue button showing an empty red dot instead of a minus.
- Doubled corners on the notifications panel.
- Stacked edges between the pages, the sidebar and the queue, including in fullscreen.
- Dark-only separator line between the sidebar and the pages.
- Song list stripes in two clashing tones in dark mode.
- Hover highlights with square edges and an off-palette grey.
- Unreadable text on accent-coloured buttons such as Play and Shuffle.
- Unreadable captions on bright album covers.
- Unreadable controls in the immersive player in light mode.
- Marketplace cards blending into the page.
- Contrast fixes for links on hovered rows, selected-row markers, switches and input borders.
- Accent-coloured small text raised to 4.5:1.
- Light text on accent-coloured fills in lyric and picker buttons.
- Notification icons all shown in green regardless of type.
- Icons in lists losing their own colours (delete, checkmarks).
- Rounded buttons turning square when focused with the keyboard.
- Hover and press scaling on buttons snapping instead of animating.
- Immersive player using Frost regardless of the selected accent.
- Accents depending on stylesheet load order.
- Text on red and green notice banners.
- Artwork captions below 4.5:1 on bright covers.
- Immersive player bar taking its colours from the artwork.
- Sidebar colours shifting when Cider adds a toolbar widget.

### Changed
- Cider's High Contrast mode raises theme text and border contrast.

### Known limitations
- Right-click menus are native system menus and follow the system theme.
- Window translucency depends on the OS or compositor. On Linux, Cider's window has no alpha.

## 1.0.0

### Added
- Nord Polar Night theme with Frost accent for pages, sidebar, player, lyrics, queue, dialogs,
  settings, menus and search.

### Fixed
- Green-tinted dialogs caused by Cider's accent colour mixing.
- Black backgrounds when Cider's window transparency is enabled.
