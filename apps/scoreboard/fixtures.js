/**
 * Home / Away fixtures screen: a MEN panel and a WOMEN panel, each in
 * kick-off order. Which side it shows comes from <body data-side="home|away">.
 */

const DATA_URL = '../../data/scoreboard/weekend_fixtures.json';
const SIDE = document.body.dataset.side === 'away' ? 'away' : 'home';
const GENDERS = ['M', 'F'];
const FIT = { max: 128, min: 84, dense: 110 };

// Fixtures that already had a score at the previous refresh. A score missing
// from here arrived since then, and its row gets a brief highlight.
const knownResults = new Set();
let rendered = false;

const RESULT_WORDS = { w: 'Won', d: 'Drew', l: 'Lost' };

function hasScore(fixture) {
    return Number.isInteger(fixture.home_score) && Number.isInteger(fixture.away_score);
}

function outcome(ours, theirs) {
    if (ours > theirs) {
        return 'w';
    }
    return ours < theirs ? 'l' : 'd';
}

function fixtureKey(fixture) {
    return fixture.fixtureId || `${fixture.date}|${fixture.team}`;
}

function genderOf(fixture) {
    return Board.genderCode(fixture.category)
        || Board.genderCode((/\(([^)]+)\)\s*$/.exec(fixture.team || '') || [])[1]);
}

function teamLine(modifier, name, score) {
    const line = Board.el('div', `team ${modifier}`);
    line.append(
        Board.el('div', 'team-name', name),
        Board.el('div', 'team-score', score === null || score === undefined ? '' : String(score))
    );
    return line;
}

/**
 * `dayTag` is set ("Sun") only for games after the weekend's first day. The
 * 1st XIs' national leagues often play on Sunday, and a small label over the
 * time marks those without splitting the list into day sections.
 */
function fixtureRow(fixture, dayTag) {
    const oursIsHome = SIDE === 'home';
    const ourScore = oursIsHome ? fixture.home_score : fixture.away_score;
    const theirScore = oursIsHome ? fixture.away_score : fixture.home_score;
    const played = hasScore(fixture);

    const row = Board.el('div', 'row row--fixture');
    const time = Board.el('div', 'time');
    if (dayTag) {
        time.append(Board.el('span', 'day-tag', dayTag));
    }
    time.append(fixture.kickoff || '');
    row.append(time);

    // The panel heading already says MEN or WOMEN, so the squad is just "3s".
    const ourTeam = fixture.team || (oursIsHome ? fixture.home_team : fixture.away_team);
    const teams = Board.el('div', 'teams');
    teams.append(
        teamLine('team--ours', Board.squadShort(ourTeam), played ? ourScore : null),
        teamLine('team--them', oursIsHome ? fixture.away_team : fixture.home_team, played ? theirScore : null)
    );
    row.append(teams);

    const result = Board.el('div', 'result');
    if (played) {
        const code = outcome(ourScore, theirScore);
        row.classList.add('is-played');
        result.classList.add(`result--${code}`);
        result.textContent = code.toUpperCase();
        result.setAttribute('aria-label', RESULT_WORDS[code]);

        const key = fixtureKey(fixture);
        if (rendered && !knownResults.has(key)) {
            row.classList.add('is-new');
        }
        knownResults.add(key);
    }
    row.append(result);
    return row;
}

function subtitleFor(days, data) {
    if (days.length === 1) {
        return Board.formatDay(days[0]);
    }
    if (days.length > 1) {
        // "Sat 12 & Sun 13 September". Rows from the later day carry a tag.
        const first = Board.localDate(days[0]);
        const last = Board.localDate(days[days.length - 1]);
        const dayPart = (date) => date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' });
        const month = (date) => date.toLocaleDateString('en-GB', { month: 'long' });
        const firstText = first.getMonth() === last.getMonth()
            ? dayPart(first)
            : `${dayPart(first)} ${month(first)}`;
        return `${firstText} & ${dayPart(last)} ${month(last)}`;
    }
    // Nothing on: the weekend the file covers still dates the screen.
    return Board.formatDay(data.weekend?.saturday);
}

function shortWeekday(isoDay) {
    return Board.localDate(isoDay)?.toLocaleDateString('en-GB', { weekday: 'short' }) || '';
}

function fillPanel(gender, fixtures, firstDay) {
    const list = document.getElementById(`fixtures-${gender}`);
    const note = document.getElementById(`${gender}-note`);
    list.replaceChildren();
    note.textContent = fixtures.length
        ? `${fixtures.length} ${fixtures.length === 1 ? 'game' : 'games'}`
        : '';

    if (!fixtures.length) {
        list.append(Board.el('p', 'empty', `No ${Board.genderWord(gender).toLowerCase()} ${SIDE} games`));
        return;
    }

    fixtures.forEach((fixture, index) => {
        const day = String(fixture.date || '').slice(0, 10);
        const row = fixtureRow(fixture, day !== firstDay ? shortWeekday(day) : '');
        row.style.setProperty('--i', index);
        list.append(row);
    });
}

function render(data) {
    const fixtures = [...(data[SIDE] || [])]
        .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const days = [...new Set(fixtures.map((fixture) => String(fixture.date || '').slice(0, 10)))];

    document.getElementById('subtitle').textContent = subtitleFor(days, data) || 'This weekend';

    GENDERS.forEach((gender) => {
        fillPanel(gender, fixtures.filter((fixture) => genderOf(fixture) === gender), days[0]);
    });

    // The two panels share the screen, so they share one row height: fit each
    // from scratch, then give both the smaller so neither overflows and the
    // rows line up.
    const lists = GENDERS.map((gender) => document.getElementById(`fixtures-${gender}`));
    lists.forEach(Board.clearRowHeight);
    const heights = lists.map((list) => Board.fitRows(list, FIT)).filter(Boolean);
    if (heights.length) {
        const height = Math.min(...heights);
        lists.forEach((list) => Board.setRowHeight(list, height, FIT.dense));
    }

    document.querySelectorAll('.team-name').forEach((node) => Board.fitText(node, 0.7));
    rendered = true;
}

async function load() {
    try {
        render(await Board.fetchJson(DATA_URL));
    } catch (error) {
        // Leave whatever is on screen rather than blanking the board.
        console.error('Could not load fixtures:', error);
    }
}

Board.run(load);
