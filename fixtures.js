// Load and populate fixtures
async function loadFixtures() {
    try {
        const response = await fetch(`weekend_fixtures.json?t=${Date.now()}`, { cache: 'no-store' });
        const data = await response.json();
        
        // Get the fixtures container
        const fixturesContainer = document.querySelector('.fixtures-container');
        
        // Clear existing fixtures (except the header)
        const existingFixtures = fixturesContainer.querySelectorAll('.fixture');
        existingFixtures.forEach(fixture => fixture.remove());
        
        // Determine which fixtures to load based on the page
        const isHomePage = document.body.classList.contains('home');
        const fixtures = isHomePage ? data.home : data.away;
        
        // Populate fixtures
        fixtures.forEach(fixture => {
            const fixtureElement = createFixtureElement(fixture);
            fixturesContainer.appendChild(fixtureElement);
        });
        
    } catch (error) {
        console.error('Error loading fixtures:', error);
    }
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
document.addEventListener('DOMContentLoaded', function() {
    setViewport();
    loadFixtures();
    // setInterval(loadFixtures, 10000); // refresh every 10 seconds (temporary for testing)
});