# Statics

One-off promo screens (open days, socials) at 1080x1920, built in the club
house style so they sit in rotation with the scoreboard and league screens.

## Making a small change

1. Double-click **`edit.bat`**. It serves the repo locally and opens both
   screens in Chrome with edit mode on.
2. Click any text and type. Hover a session row for its controls:
   * `x` deletes the row
   * `*` toggles the orange MATCH highlight (schedules with two pitch columns)
   * **+ Add session** at the foot of a column adds a row
3. Hit **Save** (or `Ctrl+S`). The first save asks where to write — pick the
   same `.html` file you are editing. Later saves go straight there.
4. Close the `edit.bat` window, then double-click **`render.bat`** to write the
   PNGs.

**Preview** in the toolbar drops edit mode so you can see the finished screen.

## Files

| File | What it is |
| --- | --- |
| `openDay.html` | Saturday club/open day |
| `youthOpenDay.html` | Sunday youth open day |
| `statics.css` | Shared layout and styling for both |
| `edit.js` | Edit mode. Only runs with `?edit` in the URL, so renders are unaffected |
| `clubday-bg.svg` | Club Day artwork: navy ground, N mark, CLUB DAY wordmark, gradient |
| `edit.bat` / `render.bat` | Edit and export helpers |
| `*-2026.png` | The exported screens |

Fonts and the pattern images come from `../shared/`.

## Notes

* Text sits on a graduated navy wash over the artwork so it stays readable
  where the gradient is brightest. If a screen ends up with less content,
  lighten the wash in `statics.css` (`.wash`) to let more of it show.
* These are not part of the Pages deploy — `pages.yml` only copies
  `apps/scoreboard` and `apps/league`. Add `apps/statics` there if the screens
  should pull them as live pages rather than images.
