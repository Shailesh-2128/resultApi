/**
 * Auto-refresh client and Theme Toggle Manager for Results Management Application.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Theme Switcher (Light / Dark Mode)
    initThemeSwitcher();

    // 2. Initialize Real-Time Result Polling for Today / Home pages
    const isTodayPage = document.querySelector('[data-page="today-results"]') || document.querySelector('[data-page="home"]');
    if (isTodayPage) {
        setInterval(fetchAndUpdateResults, 30000);
    }
});

/**
 * Handles Light Mode / Dark Mode toggling with localStorage persistence
 */
function initThemeSwitcher() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // Determine active theme (default to savedTheme or light)
    let currentTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
    applyTheme(currentTheme);

    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            currentTheme = (currentTheme === 'dark') ? 'light' : 'dark';
            localStorage.setItem('theme', currentTheme);
            applyTheme(currentTheme);
        });
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);

    const toggleIcon = document.getElementById('theme-toggle-icon');
    const toggleText = document.getElementById('theme-toggle-text');

    if (toggleIcon && toggleText) {
        if (theme === 'dark') {
            toggleIcon.className = 'bi bi-sun-fill text-warning';
            toggleText.innerText = 'Light Mode';
        } else {
            toggleIcon.className = 'bi bi-moon-stars-fill text-primary';
            toggleText.innerText = 'Dark Mode';
        }
    }
}

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
