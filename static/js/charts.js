/* Shared chart utilities and rendering — used by both index.html and stats.html */

/**
 * Escapes HTML special characters to prevent XSS when inserting user text into the DOM.
 * Uses the browser's own text encoding via a detached DOM element.
 * @param {string} text - Raw user-supplied text.
 * @returns {string} HTML-safe string.
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/*
 * Category colors are read from CSS custom properties (--cat-*) defined in shared.css.
 * This keeps colors in a single source of truth — CSS controls both stylesheet rules
 * and the Chart.js datasets, so changing a color in CSS updates everything automatically.
 */
const _rootStyle = getComputedStyle(document.documentElement);
/** @param {string} name - CSS custom property name (e.g. '--cat-strength'). */
function cssVar(name) { return _rootStyle.getPropertyValue(name).trim(); }

const catColors = {
    strength: cssVar('--cat-strength'),
    isometric: cssVar('--cat-isometric'),
    skill: cssVar('--cat-skill'),
    fitness: cssVar('--cat-fitness'),
    flexibility: cssVar('--cat-flexibility'),
    physio: cssVar('--cat-physio'),
    music: cssVar('--cat-music')
};

/**
 * Semi-transparent background variants of each category color (20% opacity).
 * Converts hex (#rrggbb) → rgba(r,g,b,0.2) for chart fill areas.
 */
const catColorsBg = Object.fromEntries(
    Object.entries(catColors).map(([k, v]) => {
        const r = parseInt(v.slice(1,3),16), g = parseInt(v.slice(3,5),16), b = parseInt(v.slice(5,7),16);
        return [k, `rgba(${r},${g},${b},0.2)`];
    })
);

/** Display order for categories — roughly ordered from most physical to least. */
const categoryOrder = ['strength', 'isometric', 'skill', 'fitness', 'flexibility', 'physio', 'music'];

/** Exercises with no log entry in the last 35 days are considered dormant. */
const DORMANT_DAYS = 35;

/**
 * Zips parallel date and value arrays into Chart.js-compatible {x, y} point objects.
 * @param {string[]} dates - ISO date strings for the x-axis.
 * @param {number[]} values - Corresponding numeric values for the y-axis.
 * @returns {{x: string, y: number}[]}
 */
function toXY(dates, values) {
    return dates.map((d, i) => ({ x: d, y: values[i] }));
}

/**
 * Computes a trailing moving-average trend line from raw values.
 *
 * The window size adapts to dataset length: `floor(length / divisor)`, with a
 * minimum of 2 to avoid a no-op. A divisor of 4 gives ~25% of data per window
 * (used for weight charts); 5 gives ~20% (used for volume charts).
 *
 * At the start of the series the window is smaller than `ws`, so it averages
 * fewer points — this "edge padding" avoids the trend line starting with a gap.
 *
 * @param {number[]} values - Raw data points.
 * @param {number} [divisor=5] - Fraction of series length for window size.
 * @returns {number[]} Smoothed values (same length as input).
 */
function makeTrend(values, divisor) {
    const ws = Math.max(2, Math.floor(values.length / (divisor || 5)));
    return values.map((v, i) => {
        const s = Math.max(0, i - ws + 1); // clamp start to 0 (edge padding)
        const sl = values.slice(s, i + 1);
        return sl.reduce((a, b) => a + b, 0) / sl.length;
    });
}

/**
 * Filters parallel date/value arrays to only include entries on or after `cutoff`.
 * When the user picks a time range (e.g. "3 months"), the cutoff is computed as
 * today minus N months and this function trims older entries from the chart data.
 *
 * @param {string[]} dates - ISO date strings.
 * @param {number[]} values - Corresponding values.
 * @param {Date|null} cutoff - Earliest date to include, or null for "all time".
 * @returns {{dates: string[], values: number[]}} Filtered parallel arrays.
 */
function filterByDate(dates, values, cutoff) {
    if (!cutoff) return { dates, values };
    const fd = [], fv = [];
    for (let i = 0; i < dates.length; i++) {
        if (new Date(dates[i]) >= cutoff) { fd.push(dates[i]); fv.push(values[i]); }
    }
    return { dates: fd, values: fv };
}

/**
 * Returns the number of days since an exercise was last logged.
 * Returns 9999 if the exercise has never been logged (sorts to bottom / always dormant).
 *
 * @param {string} code - Exercise code (e.g. 'DL' for deadlift).
 * @param {Object} timelineData - Map of exercise code → sorted date strings.
 * @returns {number} Days since last entry (0 = today).
 */
function daysSince(code, timelineData) {
    const today = new Date();
    today.setHours(0,0,0,0);
    const dates = timelineData[code];
    if (!dates || dates.length === 0) return 9999;
    // 86400000 = ms per day
    return Math.floor((today - new Date(dates[dates.length - 1])) / 86400000);
}

/** Sets Chart.js global defaults for the dark-themed UI. */
function initChartDefaults() {
    Chart.defaults.color = '#e0e0e0';
    Chart.defaults.borderColor = '#333';
    Chart.defaults.plugins.legend.labels.color = '#e0e0e0';
}

/**
 * Renders a stacked bar chart of weekly exercise volume, grouped by category.
 * Each bar segment is colored by category, allowing visual tracking of training balance.
 * @param {Object} weeklyVolume - Map of ISO week string → { category: count }.
 */
function renderWeeklyVolume(weeklyVolume) {
    const weeks = Object.keys(weeklyVolume).sort();
    const categories = ['strength', 'isometric', 'skill', 'fitness', 'flexibility', 'physio', 'music'];

    const datasets = categories.map(cat => ({
        label: cat.charAt(0).toUpperCase() + cat.slice(1),
        data: weeks.map(w => weeklyVolume[w][cat] || 0),
        backgroundColor: catColors[cat],
        borderRadius: 2,
    }));

    new Chart(document.getElementById('weeklyChart'), {
        type: 'bar',
        data: { labels: weeks, datasets },
        options: {
            responsive: true,
            scales: {
                x: { stacked: true, ticks: { maxTicksLimit: 12, font: { size: 10 } },
                     grid: { display: false } },
                y: { stacked: true, grid: { color: '#222' } }
            },
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } }
            }
        }
    });
}

/**
 * Renders a doughnut chart showing the distribution of exercises across categories.
 * @param {Object} categoryDist - Map of category name → exercise count.
 */
function renderCategoryBalance(categoryDist) {
    const categories = Object.keys(categoryDist);
    const values = categories.map(c => categoryDist[c]);
    const colors = categories.map(c => catColors[c]);

    new Chart(document.getElementById('categoryChart'), {
        type: 'doughnut',
        data: {
            labels: categories.map(c => c.charAt(0).toUpperCase() + c.slice(1)),
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            cutout: '55%',
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8 } }
            }
        }
    });
}

/**
 * Renders a bar chart of monthly exercise counts with the best month highlighted.
 * @param {Array<{month: string, count: number}>} monthlyVolume
 */
function renderMonthlySummary(monthlyVolume) {
    const months = monthlyVolume.map(m => m.month);
    const counts = monthlyVolume.map(m => m.count);
    const maxMonth = monthlyVolume.reduce((a, b) => a.count > b.count ? a : b, {count: 0});

    const bgColors = counts.map((c, i) =>
        monthlyVolume[i].month === maxMonth.month ? '#00d4ff' : 'rgba(0,212,255,0.4)');

    new Chart(document.getElementById('monthlyChart'), {
        type: 'bar',
        data: {
            labels: months,
            datasets: [{
                label: 'Exercises',
                data: counts,
                backgroundColor: bgColors,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 11 } } },
                y: { grid: { color: '#222' }, beginAtZero: true }
            },
            plugins: {
                legend: { display: false },
                subtitle: {
                    display: maxMonth.month ? true : false,
                    text: maxMonth.month ? `Best month: ${maxMonth.month} (${maxMonth.count} exercises)` : '',
                    color: '#00d4ff', font: { size: 13 }, padding: { bottom: 10 }
                }
            }
        }
    });
}

/**
 * Initialises all per-exercise progress charts (weight progression + volume).
 * Manages chart lifecycle: creates them on first load and destroys/recreates
 * them when the user changes the time-range filter.
 *
 * @param {Object} opts
 * @param {Array} opts.exercises - All exercise definitions.
 * @param {Object} opts.timelineData - Map of code → sorted date strings.
 * @param {Object} opts.progressData - Map of code → { dates, values, input_type }.
 * @param {Object} opts.weightProgress - Map of code → { dates, weights }.
 */
function initProgressCharts(opts) {
    const { exercises, timelineData, progressData, weightProgress } = opts;
    // Build a lookup map so we can quickly get exercise metadata by code
    const exMap = {};
    exercises.forEach(ex => exMap[ex.code] = ex);
    const today = new Date();
    today.setHours(0,0,0,0);

    /** Convenience wrapper that closes over the shared timelineData. */
    function _daysSince(code) {
        return daysSince(code, timelineData);
    }

    /** Tracks all live Chart.js instances so they can be destroyed before re-render. */
    let chartInstances = [];

    /**
     * (Re-)renders all progress charts for the given time window.
     *
     * Chart lifecycle: every call first destroys all existing Chart.js instances
     * to free canvas resources, clears the grid containers, then rebuilds from scratch.
     *
     * @param {number} months - Number of months to show (0 = all time, 3/6/12 etc).
     */
    function renderAll(months) {
        // Destroy previous charts to avoid canvas memory leaks
        chartInstances.forEach(c => c.destroy());
        chartInstances = [];

        // Compute the date cutoff: months=0 means "all time" (cutoff = null)
        const cutoff = months > 0 ? new Date(today.getFullYear(), today.getMonth() - months, today.getDate()) : null;
        const xMin = cutoff ? cutoff.toISOString().split('T')[0] : null;
        const xMax = today.toISOString().split('T')[0];
        // Shared x-axis config: time-scale pinned to [cutoff … today] so all charts align
        const xScaleOpts = { type: 'time', display: false,
            time: { unit: 'day' },
            ...(xMin ? { min: xMin } : {}), max: xMax };

        // Clear all grid containers and hide sections until populated
        ['weightProgressGrid', 'activeProgressGrid', 'dormantProgressGrid'].forEach(id => {
            document.getElementById(id).innerHTML = '';
        });
        ['weightProgressSection', 'activeProgressSection', 'dormantProgressSection'].forEach(id => {
            document.getElementById(id).style.display = 'none';
        });

        // --- Weight Progression ---
        // Only show weight charts for non-dormant exercises, sorted by recency.
        // Skip exercises with fewer than 2 data points — can't draw a meaningful line.
        const weightGrid = document.getElementById('weightProgressGrid');
        const weightCodes = Object.keys(weightProgress).filter(c => _daysSince(c) < DORMANT_DAYS).sort((a, b) => _daysSince(a) - _daysSince(b));
        weightCodes.forEach(code => {
            const wp = weightProgress[code];
            const ex = exMap[code];
            if (!ex) return;
            const f = filterByDate(wp.dates, wp.weights, cutoff);
            if (f.dates.length < 2) return; // need ≥2 points for a line chart
            const card = document.createElement('div');
            card.className = 'progress-card';
            const cid = `wprog-${code}-${months}`;
            card.innerHTML = `<h3>${escapeHtml(ex.code)} — ${escapeHtml(ex.name)} <span style="color:#888;font-weight:400;font-size:0.75rem;">(kg)</span></h3>
                              <canvas id="${cid}" height="160"></canvas>`;
            weightGrid.appendChild(card);
            // Weight chart: filled area + dashed trend overlay.
            // tension: 0.3 gives a gentle curve; divisor 4 = ~25% window for smoother weight trend.
            chartInstances.push(new Chart(document.getElementById(cid), {
                type: 'line',
                data: { datasets: [
                    { label: 'Weight (kg)', data: toXY(f.dates, f.values), borderColor: catColors.isometric,
                      backgroundColor: catColorsBg.isometric, fill: true, tension: 0.3,
                      pointRadius: 3, pointHoverRadius: 6, borderWidth: 2 },
                    { label: 'Trend', data: toXY(f.dates, makeTrend(f.values, 4)), borderColor: cssVar('--text-accent'),
                      borderDash: [5, 3], pointRadius: 0, borderWidth: 1.5, fill: false }
                ]},
                options: { responsive: true,
                    scales: { x: xScaleOpts, y: { grid: { color: '#222' }, beginAtZero: false } },
                    plugins: { legend: { display: false } } }
            }));
        });
        // Only show the section header if at least one chart was rendered
        if (weightGrid.children.length > 0) document.getElementById('weightProgressSection').style.display = '';

        // --- Volume Charts (Active & Dormant) ---
        // Split exercises into active (< 35 days since last log) and dormant (≥ 35 days).
        // Active sorted most-recent-last so newest appears at the bottom; dormant similar.
        const activeGrid = document.getElementById('activeProgressGrid');
        const dormantGrid = document.getElementById('dormantProgressGrid');
        const allCodes = Object.keys(progressData);
        const activeCodes = allCodes.filter(c => _daysSince(c) < DORMANT_DAYS).sort((a, b) => _daysSince(b) - _daysSince(a));
        const dormantCodes = allCodes.filter(c => _daysSince(c) >= DORMANT_DAYS).sort((a, b) => _daysSince(b) - _daysSince(a));

        /**
         * Renders a single volume-over-time chart for one exercise.
         * Skips exercises with < 3 data points in the current range — too few for
         * a useful chart (need at least a few points for the trend line to mean anything).
         */
        function renderVolume(code, grid) {
            const data = progressData[code];
            const ex = exMap[code];
            if (!ex) return;
            const f = filterByDate(data.dates, data.values, cutoff);
            if (f.dates.length < 3) return;
            const unitLabel = data.input_type === 'distance' ? 'km' :
                              data.input_type === 'minutes' ? 'min' :
                              data.input_type === 'reps_sets' ? 'total reps' : 'total seconds';
            const card = document.createElement('div');
            card.className = 'progress-card';
            const cid = `prog-${code}-${months}`;
            card.innerHTML = `<h3>${escapeHtml(ex.code)} — ${escapeHtml(ex.name)} <span style="color:#888;font-weight:400;font-size:0.75rem;">(${escapeHtml(unitLabel)})</span></h3>
                              <canvas id="${cid}" height="160"></canvas>`;
            grid.appendChild(card);
            // Volume chart: colored by exercise category, with a 20%-window trend line.
            // tension 0.3 = gentle curves; opacity 0.2 fill via catColorsBg.
            chartInstances.push(new Chart(document.getElementById(cid), {
                type: 'line',
                data: { datasets: [
                    { label: unitLabel, data: toXY(f.dates, f.values), borderColor: catColors[ex.category],
                      backgroundColor: catColorsBg[ex.category], fill: true, tension: 0.3,
                      pointRadius: 2, pointHoverRadius: 5, borderWidth: 2 },
                    { label: 'Trend', data: toXY(f.dates, makeTrend(f.values, 5)), borderColor: '#00d4ff',
                      borderDash: [5, 3], pointRadius: 0, borderWidth: 1.5, fill: false }
                ]},
                options: { responsive: true,
                    scales: { x: xScaleOpts, y: { grid: { color: '#222' }, beginAtZero: false } },
                    plugins: { legend: { display: false } } }
            }));
        }

        activeCodes.forEach(c => renderVolume(c, activeGrid));
        dormantCodes.forEach(c => renderVolume(c, dormantGrid));
        if (activeGrid.children.length > 0) document.getElementById('activeProgressSection').style.display = '';
        if (dormantGrid.children.length > 0) document.getElementById('dormantProgressSection').style.display = '';

        // Exercises that have log entries but didn't get a chart (e.g. too few data points
        // after the cutoff filter, or missing from progressData). Show them in a note so the
        // user knows they aren't forgotten.
        const codesWithChart = new Set([...allCodes, ...weightCodes]);
        const codesWithEntries = new Set(Object.keys(timelineData));
        const noChartCodes = [];
        exercises.forEach(ex => {
            if (codesWithEntries.has(ex.code) && !codesWithChart.has(ex.code)) noChartCodes.push(ex.code);
        });
        const note = document.getElementById('noChartNote');
        if (noChartCodes.length > 0) {
            note.textContent = 'No progress chart for: ' + noChartCodes.join(', ');
            note.style.display = '';
        } else { note.style.display = 'none'; }
    }

    // Default view: last 3 months of progress
    renderAll(3);

    // Time-range toggle buttons (3m / 6m / 12m / All)
    document.querySelectorAll('#progressRangeBtns .range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#progressRangeBtns .range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderAll(parseInt(btn.dataset.months));
        });
    });
}

/** Scrolls all horizontally-overflowing heatmap/timeline containers to the right (most recent data). */
function scrollContainersToEnd() {
    document.querySelectorAll('.heatmap-container, .timeline-container').forEach(el => {
        el.scrollLeft = el.scrollWidth;
    });
}
