/**
 * Top Scorers screen: four panels. The season's leading scorers for men and
 * women across the top, and the most recent match day's scorers beneath.
 */

const DATA_URL = '../../data/scorers/scorers.json';

// Rows are a fixed height (see styles.css), so these are what fit.
const SEASON_ROWS = 7;      // the leader plus six
const DAY_ROWS = 4;

function scorerRow(scorer, rank, lead) {
    const row = Board.el('div', lead ? 'row row--scorer row--lead' : 'row row--scorer');

    const who = Board.el('div', 'who');
    who.append(Board.el('div', 'name', scorer.name || 'Unknown'));
    if (scorer.squad) {
        who.append(Board.el('div', 'squad', scorer.squad));
    }

    row.append(
        Board.el('div', 'rank', String(rank)),
        who,
        Board.el('div', 'figure', String(scorer.goals ?? 0))
    );
    return row;
}

function totalGoals(scorers) {
    return (scorers || []).reduce((sum, scorer) => sum + (Number(scorer.goals) || 0), 0);
}

/**
 * Fill one panel. `lead` gives joint-first scorers the medal and the larger
 * type; it is off for the match-day panels, where two goals isn't a podium.
 */
function fillPanel(id, scorers, { limit, lead, empty }) {
    const list = document.getElementById(id);
    const note = document.getElementById(`${id}-note`);
    list.replaceChildren();
    note.textContent = '';

    const shown = [...(scorers || [])]
        .sort((a, b) => (b.goals ?? 0) - (a.goals ?? 0))
        .slice(0, limit);
    if (!shown.length) {
        list.append(Board.el('p', 'empty', empty));
        return;
    }

    const ranks = Board.competitionRanks(shown, (scorer) => scorer.goals ?? 0);
    shown.forEach((scorer, index) => {
        const row = scorerRow(scorer, ranks[index], lead && ranks[index] === 1);
        row.style.setProperty('--i', index);
        list.append(row);
    });
    note.textContent = `${totalGoals(scorers)} goals`;

    // The leader's name wraps onto a second line instead (see styles.css).
    list.querySelectorAll('.row:not(.row--lead) .name').forEach(Board.fitName);
}

function render(data) {
    document.getElementById('subtitle').textContent = data.season_label || 'Season';

    // Dating the section means a board still showing last week's goals says so.
    // The generator writes a label covering the whole weekend ("Sat 12 & Sun 13
    // September") when both days had results.
    document.getElementById('day-date').textContent =
        data.match_day?.label || Board.formatDay(data.match_day?.date);

    const season = data.season || {};
    const matchDay = data.match_day_scorers || {};
    ['M', 'F'].forEach((gender) => {
        fillPanel(`season-${gender}`, season[gender], {
            limit: SEASON_ROWS,
            lead: true,
            empty: 'No goals yet this season'
        });
        fillPanel(`day-${gender}`, matchDay[gender], {
            limit: DAY_ROWS,
            lead: false,
            empty: 'No goals recorded'
        });
    });
}

async function load() {
    try {
        render(await Board.fetchJson(DATA_URL));
    } catch (error) {
        // Leave whatever is on screen: slightly stale goals beat a blank board.
        console.error('Could not load scorers:', error);
    }
}

Board.run(load);
