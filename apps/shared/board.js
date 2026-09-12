/**
 * Shared helpers for the club screens (fixtures, league, scorers).
 *
 * Loaded before each page's own script. Everything hangs off `Board` so the
 * page scripts stay short and read as "what goes on this screen".
 */
const Board = (() => {
    // A minute: the data files are a few KB, and this is the last fixed delay
    // between a result being entered and the screen showing it.
    const REFRESH_MS = 60000;
    const CLUB_URL = '../../config/club.json';

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = text;
        }
        return node;
    }

    async function fetchJson(url) {
        const separator = url.includes('?') ? '&' : '?';
        const response = await fetch(`${url}${separator}t=${Date.now()}`, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`${url}: HTTP ${response.status}`);
        }
        return response.json();
    }

    /** Fetch that resolves to `fallback` instead of throwing. */
    async function fetchJsonOr(url, fallback) {
        try {
            return await fetchJson(url);
        } catch (error) {
            return fallback;
        }
    }

    /** "2026-09-12T10:30:00" -> a Date at local midnight, so UTC can't shift the day. */
    function localDate(iso) {
        const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
        return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null;
    }

    /** "2026-09-12" -> "Saturday 12 September". */
    function formatDay(iso) {
        const date = localDate(iso);
        return date
            ? date.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
            : '';
    }

    /** Accepts "M", "F", "men", "women", "(M)"... and returns "M", "F" or "". */
    function genderCode(value) {
        const text = String(value || '').replace(/[()]/g, '').trim().toUpperCase();
        if (text.startsWith('M')) {
            return 'M';
        }
        if (text.startsWith('F') || text.startsWith('W')) {
            return 'F';
        }
        return '';
    }

    function genderWord(gender) {
        const code = genderCode(gender);
        if (code === 'M') {
            return 'Men’s';
        }
        return code === 'F' ? 'Women’s' : '';
    }

    /**
     * "St Albans 3 (M)" -> "Men's 3s". GMS names squads by club and number
     * only, so two "St Albans 3" fixtures on one afternoon are indistinguishable
     * without the gender. The men's 1st XI is published with no number at all,
     * which is why a missing number means 1s.
     */
    function squadLabel(teamName, gender) {
        const name = String(teamName || '');
        const code = genderCode(gender) || genderCode((/\(([^)]+)\)\s*$/.exec(name) || [])[1]);
        return [genderWord(code), squadShort(name)].filter(Boolean).join(' ');
    }

    /** "St Albans 3 (M)" -> "3s", for rows already under a MEN / WOMEN heading. */
    function squadShort(teamName) {
        const number = (/(\d+)\s*(?:\([^)]*\))?\s*$/.exec(String(teamName || '')) || [])[1] || '1';
        return `${number}s`;
    }

    /** "Tom Fairweather" -> "T. Fairweather". */
    function shortenName(full) {
        const parts = String(full || '').trim().split(/\s+/);
        if (parts.length < 2) {
            return full;
        }
        return `${parts[0][0]}. ${parts[parts.length - 1]}`;
    }

    // Strict: the CSS ellipsis kicks in at a fraction of a pixel of overflow,
    // so any slack here lets a "fitting" name render clipped.
    function overflows(node) {
        return node.scrollWidth > node.clientWidth;
    }

    /** Step the font size down until the text fits, to `minScale` of its styled size. */
    function fitText(node, minScale = 0.75) {
        node.style.fontSize = '';
        const base = parseFloat(getComputedStyle(node).fontSize);
        let size = base;
        while (overflows(node) && size > base * minScale) {
            size -= 1;
            node.style.fontSize = `${size}px`;
        }
        return !overflows(node);
    }

    /**
     * For people's names: shrink a little, then abbreviate the first name and
     * shrink further, then let the CSS ellipsis take whatever is left.
     * Abbreviating early keeps a long name close to its neighbours' size;
     * "R. Macallister-Smith" reads better than a full name in tiny type.
     */
    function fitName(node) {
        const full = node.dataset.full || node.textContent;
        node.dataset.full = full;
        node.textContent = full;
        if (!fitText(node, 0.9)) {
            node.textContent = shortenName(full);
            fitText(node);
        }
    }

    /**
     * Share a list's height between its rows: as tall as `max` when there are
     * few, down to `min` on a busy weekend. Below `dense` the list gets the
     * `is-dense` class so the type can step down with the rows. Anything in
     * the list that isn't a row (a day divider) keeps its own height.
     */
    function fitRows(container, { max = 150, min = 88, dense = 120 } = {}) {
        // Measure from the default height every time: a list that was shrunk
        // on a busy refresh would otherwise stay shrunk when things quieten.
        clearRowHeight(container);
        const children = [...container.children];
        const rows = children.filter((child) => child.classList.contains('row'));
        if (!rows.length) {
            return 0;
        }
        const fixed = children
            .filter((child) => !child.classList.contains('row'))
            .reduce((total, child) => total + child.offsetHeight, 0);
        const share = Math.floor((container.clientHeight - fixed) / rows.length);
        const height = Math.max(min, Math.min(max, share));
        setRowHeight(container, height, dense);
        return height;
    }

    function clearRowHeight(container) {
        container.style.removeProperty('--row-h');
        container.classList.remove('is-dense');
    }

    function setRowHeight(container, height, dense) {
        container.style.setProperty('--row-h', `${height}px`);
        container.classList.toggle('is-dense', height < dense);
    }

    /**
     * Rank with ties: 16, 15, 15, 12 -> 1, 2, 2, 4. `value` reads the number
     * being ranked from each item.
     */
    function competitionRanks(items, value) {
        let previous = null;
        let rank = 0;
        return items.map((item, index) => {
            const current = value(item);
            if (current !== previous) {
                rank = index + 1;
                previous = current;
            }
            return rank;
        });
    }

    function fontsReady() {
        if (!document.fonts) {
            return Promise.resolve();
        }
        // Each face is only fetched once something uses it, and rows don't
        // exist yet, so ask for them by name. Measuring against a fallback font
        // would make every fitText() call wrong.
        const faces = ['500', '600', '700', '800'].map((weight) => `${weight} 40px Barlow`);
        faces.push('italic bold 40px "TT Bluescreens"');
        return Promise.all(faces.map((face) => document.fonts.load(face))).catch(() => {});
    }

    /**
     * Render now and every five minutes after. Entrance animations are gated
     * on the board not yet being `settled`, so they run once when the screen
     * comes up, not on every refresh.
     */
    function run(load) {
        fontsReady().then(async () => {
            // "League of Leagues" is wider than the screen at the title size.
            document.querySelectorAll('.head-title').forEach((title) => fitText(title, 0.6));

            // The club name comes from config/club.json, like every other club
            // specific, rather than being written into five HTML files.
            const club = await fetchJsonOr(CLUB_URL, null);
            if (club?.name) {
                document.querySelectorAll('.bar-club').forEach((node) => {
                    node.textContent = club.name;
                });
            }

            try {
                await load();
            } finally {
                setTimeout(() => document.body.classList.add('settled'), 1600);
                setInterval(load, REFRESH_MS);
            }
        });
    }

    return {
        el,
        fetchJson,
        fetchJsonOr,
        formatDay,
        localDate,
        genderCode,
        genderWord,
        squadLabel,
        fitText,
        fitName,
        fitRows,
        clearRowHeight,
        setRowHeight,
        squadShort,
        competitionRanks,
        run
    };
})();
