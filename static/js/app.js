/**
 * Auto-refresh client for Results Management application.
 * Polls internal Django REST API endpoint /api/results/today/ every 30 seconds
 * and updates DOM result cards dynamically without page reload.
 */

document.addEventListener('DOMContentLoaded', () => {
    const isTodayPage = document.querySelector('[data-page="today-results"]') || document.querySelector('[data-page="home"]');
    
    if (isTodayPage) {
        // Poll every 30 seconds
        setInterval(fetchAndUpdateResults, 30000);
    }
});

async function fetchAndUpdateResults() {
    const statusText = document.getElementById('live-status-text');
    if (statusText) {
        statusText.innerText = 'Refreshing...';
    }

    try {
        const response = await fetch('/api/results/today/', {
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (data && data.results) {
            updateDOMWithResults(data.results);
            const lastUpdated = document.getElementById('last-updated-time');
            if (lastUpdated) {
                const now = new Date();
                lastUpdated.innerText = `Updated at ${now.toLocaleTimeString()}`;
            }
        }
    } catch (err) {
        console.warn('Background auto-refresh failed:', err);
    } finally {
        if (statusText) {
            statusText.innerText = 'Live Auto-Update Active';
        }
    }
}

function updateDOMWithResults(resultsList) {
    resultsList.forEach(item => {
        const marketSlug = item.slug;
        
        // Update Open Result
        const openValElem = document.getElementById(`open-val-${marketSlug}`);
        const openBadgeElem = document.getElementById(`open-badge-${marketSlug}`);

        if (openValElem && openBadgeElem) {
            if (item.open) {
                openValElem.innerText = item.open;
                openBadgeElem.className = 'result-badge badge-success';
                openBadgeElem.innerText = 'Available';
            } else if (item.open_status === 'FETCHING') {
                openValElem.innerText = 'Updating...';
                openBadgeElem.className = 'result-badge badge-updating';
                openBadgeElem.innerText = 'Updating';
            } else if (item.open_status === 'FAILED' || item.open_status === 'TIMEOUT') {
                openValElem.innerText = 'Temporarily unavailable';
                openBadgeElem.className = 'result-badge badge-unavailable';
                openBadgeElem.innerText = 'Error';
            } else {
                openValElem.innerText = 'Waiting for result';
                openBadgeElem.className = 'result-badge badge-waiting';
                openBadgeElem.innerText = 'Waiting';
            }
        }

        // Update Close Result
        const closeValElem = document.getElementById(`close-val-${marketSlug}`);
        const closeBadgeElem = document.getElementById(`close-badge-${marketSlug}`);

        if (closeValElem && closeBadgeElem) {
            if (item.close) {
                closeValElem.innerText = item.close;
                closeBadgeElem.className = 'result-badge badge-success';
                closeBadgeElem.innerText = 'Available';
            } else if (item.close_status === 'FETCHING') {
                closeValElem.innerText = 'Updating...';
                closeBadgeElem.className = 'result-badge badge-updating';
                closeBadgeElem.innerText = 'Updating';
            } else if (item.close_status === 'FAILED' || item.close_status === 'TIMEOUT') {
                closeValElem.innerText = 'Temporarily unavailable';
                closeBadgeElem.className = 'result-badge badge-unavailable';
                closeBadgeElem.innerText = 'Error';
            } else {
                closeValElem.innerText = 'Waiting for result';
                closeBadgeElem.className = 'result-badge badge-waiting';
                closeBadgeElem.innerText = 'Waiting';
            }
        }
    });
}
