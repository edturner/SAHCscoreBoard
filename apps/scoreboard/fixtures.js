// Load and populate fixtures
async function loadFixtures() {
    try {
        const response = await fetch(`../../data/scoreboard/weekend_fixtures.json?t=${Date.now()}`, { cache: 'no-store' });
        const data = await response.json();

        // Get the fixtures container
        const fixturesContainer = document.querySelector('.fixtures-container');

        // Clear whatever the last render left behind
        fixturesContainer.querySelectorAll('.fixture, .empty-state')
            .forEach(el => el.remove());

        // Determine which fixtures to load based on the page
        const isHomePage = document.body.classList.contains('home');
        const fixtures = (isHomePage ? data.home : data.away) || [];

        // Sort fixtures by time
        fixtures.sort((a, b) => new Date(a.date) - new Date(b.date));

        // Prefer the first fixture's date; fall back to the weekend the file covers
        // so the header is still right when there is nothing on.
        const dateHeaderEl = fixturesContainer.querySelector('.date-header');
        if (dateHeaderEl) {
            const formatted = formatDateHeader(fixtures[0]?.date)
                || formatDateHeader(data.weekend?.saturday);
            // Without a date from either source, an out-of-date placeholder is worse
            // than none at all.
            dateHeaderEl.textContent = formatted || '';
            dateHeaderEl.hidden = !formatted;
        }

        if (fixtures.length === 0) {
            fixturesContainer.appendChild(createEmptyState(isHomePage));
            return;
        }

        // Populate fixtures
        fixtures.forEach(fixture => {
            const fixtureElement = createFixtureElement(fixture);
            fixturesContainer.appendChild(fixtureElement);
        });

    } catch (error) {
        // Leave whatever is already on screen rather than blanking the board.
        console.error('Error loading fixtures:', error);
    }
}

function createEmptyState(isHomePage) {
    const wrapper = document.createElement('div');
    wrapper.className = 'empty-state';
    wrapper.innerHTML = `
        <div class="empty-state-title">No ${isHomePage ? 'home' : 'away'} fixtures</div>
        <div class="empty-state-subtitle">Check back on match day</div>
    `;
    return wrapper;
}

function createFixtureElement(fixture) {
    const fixtureDiv = document.createElement('div');
    fixtureDiv.className = 'fixture';

    // Insert gender letter between team name and number
    const genderSuffix = fixture.category === 'men' ? 'M' : 'W';
    const homeTeam = fixture.home_team.replace(/(\d+)$/, `${genderSuffix}$1`);
    const awayTeam = fixture.away_team.replace(/(\d+)$/, `${genderSuffix}$1`);

    // Determine score display
    const hasBothScores = Number.isInteger(fixture.home_score) && Number.isInteger(fixture.away_score);
    const scoreDisplay = hasBothScores ? `${fixture.home_score} : ${fixture.away_score}` : '- : -';
    const scoreClass = hasBothScores ? 'score-active' : 'score-placeholder';

    fixtureDiv.innerHTML = `
        <div class="fixture-content">
            <div class="teams">
                <div class="team-home">${homeTeam}</div>
                <div class="vs">VS</div>
                <div class="team-away">${awayTeam}</div>
            </div>
            <div class="fixture-details">
                <div class="time">${fixture.kickoff}</div>
                <div class="score-info ${scoreClass}">${scoreDisplay}</div>
            </div>
        </div>
    `;

    return fixtureDiv;
}

// Force viewport to exact dimensions
function setViewport() {
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport) {
        viewport.setAttribute('content', 'width=1080, height=1920, initial-scale=1.0, user-scalable=no');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function () {
    setViewport();
    loadFixtures();
    setInterval(loadFixtures, 300000); // refresh every 5 minutes
});

function formatDateHeader(isoDateString) {
    try {
        const d = new Date(isoDateString);
        if (isNaN(d.getTime())) return null;
        const weekday = d.toLocaleDateString('en-GB', { weekday: 'long' });
        const day = d.getDate();
        const month = d.toLocaleDateString('en-GB', { month: 'long' });
        return `${weekday} ${day}${getOrdinal(day)} ${month}`;
    } catch (e) {
        return null;
    }
}

function getOrdinal(n) {
    const s = ["th", "st", "nd", "rd"], v = n % 100;
    return s[(v - 20) % 10] || s[v] || s[0];
}