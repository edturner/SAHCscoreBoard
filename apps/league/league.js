/**
 * League of Leagues: every club team of one gender, ranked by points per game
 * so squads in different divisions can be compared. The gender comes from
 * <body data-gender="M|F">.
 *
 * Movement arrows compare against the previous snapshot (teamData.prev.json,
 * which the data workflow rotates on each update), falling back to the last
 * gameweek snapshot if there isn't one.
 */

const GENDER = (document.body.dataset.gender || '').toUpperCase();
const TEAM_DATA = '../../data/league/teamData.json';
const PREVIOUS_SNAPSHOTS = [
    '../../data/league/teamData.prev.json',
    '../../data/league/teamData.lastGameweek.json'
];

function num(value) {
    return Number.parseFloat(value) || 0;
}

function teamKey(team) {
    return team?.teamId || team?.name || '';
}

function genderOf(team) {
    const source = team?.name || team?.teamDisplay || '';
    return Board.genderCode((/\(([^)]+)\)\s*$/.exec(source) || [])[1]);
}

function squadNumber(team) {
    return Number((/(\d+)\s*(?:\([^)]*\))?\s*$/.exec(team?.name || '') || [])[1] || 1);
}

/**
 * This gender's teams that have a usable PPG, best first. Ties go to goal
 * difference and then to squad order, so a pre-season table where everyone
 * is on zero reads 1s, 2s, 3s rather than in arbitrary order.
 */
function rankTeams(teams) {
    return (Array.isArray(teams) ? teams : [])
        .filter((team) => Number.isFinite(Number.parseFloat(team?.stats?.ppg)))
        .filter((team) => !GENDER || GENDER === 'ALL' || genderOf(team) === GENDER)
        .sort((a, b) =>
            num(b.stats.ppg) - num(a.stats.ppg)
            || num(b.stats.goalDiff) - num(a.stats.goalDiff)
            || squadNumber(a) - squadNumber(b));
}

function movement(team, rank, previousRanks) {
    const before = previousRanks.get(teamKey(team));
    if (!before || before === rank) {
        return 'steady';
    }
    return before > rank ? 'up' : 'down';
}

/** "Open - Men's Conference Midlands (2026-2027)" -> "Conference Midlands". */
function divisionLabel(label) {
    return String(label || '')
        .replace(/\s*\(\d{4}\s*-\s*\d{4}\)\s*$/, '')
        .replace(/^Open\s*-\s*/i, '')
        .replace(/\b(?:Men|Women)['’]s\s+/i, '')
        .trim();
}

/**
 * Five slots, oldest to newest reading left to right. The data is newest
 * first, and a team with fewer than five games gets empty slots on the left,
 * so the latest result is always in the same place.
 */
function formCells(form) {
    const recent = (form || [])
        .slice(0, 5)
        .map((entry) => String(entry?.result || '').toUpperCase())
        .reverse();
    const blanks = 5 - recent.length;

    const box = Board.el('div', 'form');
    for (let slot = 0; slot < 5; slot += 1) {
        const result = slot < blanks ? '' : recent[slot - blanks];
        const cell = Board.el('span', 'form-cell', result);
        if (result) {
            cell.classList.add(`form--${result.toLowerCase()}`);
        }
        box.append(cell);
    }
    return box;
}

function leagueRow(team, rank, move) {
    const stats = team.stats || {};
    const played = Number.parseInt(stats.played, 10) || 0;

    const row = Board.el('div', 'row row--league');
    if (rank === 1 && played > 0) {
        row.classList.add('row--lead');
    }

    const rankCell = Board.el('div', 'rank-cell');
    rankCell.append(Board.el('div', 'rank', String(rank)));
    if (move !== 'steady') {
        const arrow = Board.el('span', `move move--${move}`);
        arrow.setAttribute('aria-label', move === 'up' ? 'Up' : 'Down');
        rankCell.append(arrow);
    }

    const division = divisionLabel(team.competition?.label);
    const teamCell = Board.el('div', 'team-cell');
    teamCell.append(
        // The panel heading already says MEN or WOMEN, so the squad is just "3s".
        Board.el('div', 'name', Board.squadShort(team.name)),
        Board.el('div', 'meta', played ? `${division} · ${played} played` : division)
    );

    const ppg = Board.el('div', 'figure', played ? num(stats.ppg).toFixed(2) : '-');
    if (!played) {
        ppg.classList.add('is-empty');
    }

    row.append(rankCell, teamCell, formCells(team.form), ppg);
    return row;
}

/** "... (2026-2027)" on any team's competition -> "2026/27 season". */
function seasonLabel(teams) {
    for (const team of teams) {
        const match = /\((\d{4})\s*-\s*\d{2}(\d{2})\)/.exec(team?.competition?.label || '');
        if (match) {
            return `${match[1]}/${match[2]} season`;
        }
    }
    return '';
}

async function previousSnapshot() {
    for (const url of PREVIOUS_SNAPSHOTS) {
        const snapshot = await Board.fetchJsonOr(url, null);
        if (Array.isArray(snapshot)) {
            return snapshot;
        }
    }
    return [];
}

async function load() {
    const list = document.getElementById('league');
    try {
        const teams = rankTeams(await Board.fetchJson(TEAM_DATA));
        const previousRanks = new Map(
            rankTeams(await previousSnapshot()).map((team, index) => [teamKey(team), index + 1])
        );

        document.getElementById('subtitle').textContent = seasonLabel(teams) || 'This season';
        document.getElementById('league-note').textContent = teams.length ? `${teams.length} teams` : '';

        list.replaceChildren();
        if (!teams.length) {
            list.append(Board.el('p', 'empty', 'No league data yet'));
            return;
        }
        teams.forEach((team, index) => {
            const row = leagueRow(team, index + 1, movement(team, index + 1, previousRanks));
            row.style.setProperty('--i', index);
            list.append(row);
        });

        Board.fitRows(list, { max: 150, min: 96, dense: 120 });
        list.querySelectorAll('.team-cell .meta').forEach((node) => Board.fitText(node, 0.8));
    } catch (error) {
        console.error('Could not load the league:', error);
        if (!list.children.length) {
            list.append(Board.el('p', 'empty', 'League table unavailable'));
        }
    }
}

Board.run(load);
