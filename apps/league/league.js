function formatNumber(value, decimals = 2) {
    const num = Number.parseFloat(value);
    if (Number.isNaN(num)) {
        return '0.00';
    }
    return num.toFixed(decimals);
}

function determineTrend(team, rank, previousLookup, previousRankMap) {
    const defaultTrend = { type: 'steady', arrow: '→', label: 'No change' };
    const teamKey = getTeamKey(team);
    if (!teamKey || !(previousLookup instanceof Map) || !(previousRankMap instanceof Map)) {
        return defaultTrend;
    }

    const previous = previousLookup.get(teamKey);
    if (!previous || !previous.stats?.ppg) {
        return defaultTrend;
    }

    const currentPpg = Number.parseFloat(team?.stats?.ppg ?? '0') || 0;
    const previousPpg = Number.parseFloat(previous.stats.ppg ?? '0') || 0;
    const previousRank = previousRankMap.get(teamKey);

    const rankDelta = typeof previousRank === 'number' ? previousRank - rank : 0;
    const ppgDelta = currentPpg - previousPpg;
    const ppgThreshold = 0.01;

    if (rankDelta > 0 || (rankDelta === 0 && ppgDelta > ppgThreshold)) {
        return { type: 'up', arrow: '↑', label: 'Improved rank' };
    }
    if (rankDelta < 0 || (rankDelta === 0 && ppgDelta < -ppgThreshold)) {
        return { type: 'down', arrow: '↓', label: 'Dropped rank' };
    }
    return defaultTrend;
}

function buildFormBadges(formEntries = []) {
    return formEntries.slice(0, 5).map((entry) => {
        const result = entry?.result?.toUpperCase() ?? '';
        const badge = document.createElement('span');
        badge.classList.add('form-badge');
        if (result === 'W') {
            badge.classList.add('form-win');
        } else if (result === 'L') {
            badge.classList.add('form-loss');
        } else {
            badge.classList.add('form-draw');
        }
        badge.textContent = result || '-';
        return badge;
    });
}

function extractGender(team) {
    const source = team?.name || team?.teamDisplay || '';
    const match = source.match(/\(([^)]+)\)/);
    const code = match?.[1]?.trim().toUpperCase();
    if (!code) {
        return '';
    }
    if (code.startsWith('M')) {
        return 'M';
    }
    if (code.startsWith('F')) {
        return 'F';
    }
    return '';
}

function getTeamKey(team) {
    return team?.teamId || team?.name || '';
}

function filterTeamsByGender(rawTeams = [], genderFilter = 'ALL') {
    return rawTeams
        .filter((team) => {
            const rawPpg = team?.stats?.ppg;
            if (rawPpg === undefined || rawPpg === null || rawPpg === '') {
                return false;
            }
            return Number.isFinite(Number.parseFloat(rawPpg));
        })
        .filter((team) => {
            if (genderFilter === 'ALL') {
                return true;
            }
            const gender = extractGender(team);
            if (!gender) {
                return false;
            }
            return gender === genderFilter;
        });
}

function sortTeamsByPPG(teams = []) {
    return [...teams].sort(
        (a, b) => Number.parseFloat(b?.stats?.ppg ?? '0') - Number.parseFloat(a?.stats?.ppg ?? '0'),
    );
}

function buildRankMap(teams = []) {
    const map = new Map();
    teams.forEach((team, index) => {
        const key = getTeamKey(team);
        if (key) {
            map.set(key, index + 1);
        }
    });
    return map;
}

function buildTeamLookup(teams = []) {
    const map = new Map();
    teams.forEach((team) => {
        const key = getTeamKey(team);
        if (key) {
            map.set(key, team);
        }
    });
    return map;
}

function createLeagueRow(team, rank, trendInfo) {
    const { name, teamDisplay, competition = {}, stats = {}, form = [] } = team;
    const displayName = teamDisplay || name || 'Unknown Team';
    const compLabel = competition.label || 'League TBD';
    const played = Number.parseInt(stats.played, 10) || 0;
    const won = Number.parseInt(stats.won, 10) || 0;
    const drawn = Number.parseInt(stats.drawn, 10) || 0;
    const lost = Number.parseInt(stats.lost, 10) || 0;
    const points = Number.parseInt(stats.points, 10) || 0;
    const ppg = formatNumber(stats.ppg ?? 0);
    const trend = trendInfo || { type: 'steady', arrow: '→', label: 'No change' };
    const movementClass = trend?.type ? `movement-${trend.type}` : 'movement-steady';
    const badgeClass = trend?.type ? `badge-${trend.type}` : 'badge-steady';

    const row = document.createElement('div');
    row.classList.add('table-row', movementClass);

    row.innerHTML = `
        <div class="col col-rank">
            <div class="rank-chip ${badgeClass}">
                <span class="rank-number">${rank}</span>
                <span class="rank-arrow">${trend.arrow ?? '→'}</span>
            </div>
        </div>
        <div class="col col-team">
            <div class="team-name">${displayName}</div>
            <div class="competition-label">${compLabel}</div>
        </div>
        <div class="col col-ppg">
            <div class="ppg-value">${ppg}</div>
        </div>
        <div class="col col-points">
            <div class="points-value">${points}</div>
        </div>
        <div class="col col-record">
            <div class="record-main">${won}-${drawn}-${lost}</div>
            <div class="record-sub">${played} GP</div>
        </div>
        <div class="col col-form">
            <div class="form-badges"></div>
        </div>
    `;

    const formContainer = row.querySelector('.form-badges');
    buildFormBadges(form).forEach((badge) => formContainer.appendChild(badge));

    return row;
}

async function loadLeague() {
    const grid = document.getElementById('league-grid');
    if (!grid) {
        return;
    }

    try {
        const genderFilter = document.body?.dataset?.gender?.toUpperCase?.() || 'ALL';
        const response = await fetch('../../data/league/teamData.json', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`Unable to load team data (${response.status})`);
        }

        const rawTeams = await response.json();
        let previousTeamsRaw = [];
        
        // Try to load last gameweek snapshot first, fallback to prev snapshot
        try {
            const gameweekResponse = await fetch('../../data/league/teamData.lastGameweek.json', { cache: 'no-store' });
            if (gameweekResponse.ok) {
                previousTeamsRaw = await gameweekResponse.json();
            } else {
                // Fallback to previous snapshot if gameweek snapshot doesn't exist
                const previousResponse = await fetch('../../data/league/teamData.prev.json', { cache: 'no-store' });
                if (previousResponse.ok) {
                    previousTeamsRaw = await previousResponse.json();
                }
            }
        } catch (prevError) {
            // eslint-disable-next-line no-console
            console.warn('Unable to load previous snapshot, trends will show as steady.', prevError);
        }

        const fragment = document.createDocumentFragment();
        const filteredTeams = filterTeamsByGender(rawTeams, genderFilter);
        const teams = sortTeamsByPPG(filteredTeams);

        const previousFiltered = sortTeamsByPPG(filterTeamsByGender(previousTeamsRaw, genderFilter));
        const previousRankMap = buildRankMap(previousFiltered);
        const previousLookup = buildTeamLookup(previousFiltered);

        teams.forEach((team, index) => {
            const trend = determineTrend(team, index + 1, previousLookup, previousRankMap);
            const row = createLeagueRow(team, index + 1, trend);
            fragment.appendChild(row);
        });

        grid.appendChild(fragment);
    } catch (error) {
        const errorMessage = document.createElement('div');
        errorMessage.classList.add('error-state');
        errorMessage.textContent = 'Something went wrong loading the league overview.';
        grid.appendChild(errorMessage);
        // eslint-disable-next-line no-console
        console.error(error);
    }
}

document.addEventListener('DOMContentLoaded', loadLeague);

