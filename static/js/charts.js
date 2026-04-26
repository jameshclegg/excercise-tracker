/* Shared chart utilities and rendering — used by both index.html and stats.html */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

const catColors = {
    strength: '#e74c3c',
    isometric: '#f39c12',
    skill: '#9b59b6',
    fitness: '#2ecc71',
    flexibility: '#3498db',
    physio: '#1abc9c',
    music: '#e91e63'
};

const catColorsBg = {
    strength: 'rgba(231,76,60,0.2)',
    isometric: 'rgba(243,156,18,0.2)',
    skill: 'rgba(155,89,182,0.2)',
    fitness: 'rgba(46,204,113,0.2)',
    flexibility: 'rgba(52,152,219,0.2)',
    physio: 'rgba(26,188,156,0.2)',
    music: 'rgba(233,30,99,0.2)'
};

const categoryOrder = ['strength', 'isometric', 'skill', 'fitness', 'flexibility', 'physio', 'music'];

const DORMANT_DAYS = 35;

function toXY(dates, values) {
    return dates.map((d, i) => ({ x: d, y: values[i] }));
}

function makeTrend(values, divisor) {
    const ws = Math.max(2, Math.floor(values.length / (divisor || 5)));
    return values.map((v, i) => {
        const s = Math.max(0, i - ws + 1);
        const sl = values.slice(s, i + 1);
        return sl.reduce((a, b) => a + b, 0) / sl.length;
    });
}

function filterByDate(dates, values, cutoff) {
    if (!cutoff) return { dates, values };
    const fd = [], fv = [];
    for (let i = 0; i < dates.length; i++) {
        if (new Date(dates[i]) >= cutoff) { fd.push(dates[i]); fv.push(values[i]); }
    }
    return { dates: fd, values: fv };
}

function daysSince(code, timelineData) {
    const today = new Date();
    today.setHours(0,0,0,0);
    const dates = timelineData[code];
    if (!dates || dates.length === 0) return 9999;
    return Math.floor((today - new Date(dates[dates.length - 1])) / 86400000);
}

function initChartDefaults() {
    Chart.defaults.color = '#e0e0e0';
    Chart.defaults.borderColor = '#333';
    Chart.defaults.plugins.legend.labels.color = '#e0e0e0';
}

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

function initProgressCharts(opts) {
    const { exercises, timelineData, progressData, weightProgress } = opts;
    const exMap = {};
    exercises.forEach(ex => exMap[ex.code] = ex);
    const today = new Date();
    today.setHours(0,0,0,0);

    function _daysSince(code) {
        return daysSince(code, timelineData);
    }

    let chartInstances = [];

    function renderAll(months) {
        chartInstances.forEach(c => c.destroy());
        chartInstances = [];

        const cutoff = months > 0 ? new Date(today.getFullYear(), today.getMonth() - months, today.getDate()) : null;
        const xMin = cutoff ? cutoff.toISOString().split('T')[0] : null;
        const xMax = today.toISOString().split('T')[0];
        const xScaleOpts = { type: 'time', display: false,
            time: { unit: 'day' },
            ...(xMin ? { min: xMin } : {}), max: xMax };

        ['weightProgressGrid', 'activeProgressGrid', 'dormantProgressGrid'].forEach(id => {
            document.getElementById(id).innerHTML = '';
        });
        ['weightProgressSection', 'activeProgressSection', 'dormantProgressSection'].forEach(id => {
            document.getElementById(id).style.display = 'none';
        });

        // --- Weight Progression ---
        const weightGrid = document.getElementById('weightProgressGrid');
        const weightCodes = Object.keys(weightProgress).filter(c => _daysSince(c) < DORMANT_DAYS).sort((a, b) => _daysSince(a) - _daysSince(b));
        weightCodes.forEach(code => {
            const wp = weightProgress[code];
            const ex = exMap[code];
            if (!ex) return;
            const f = filterByDate(wp.dates, wp.weights, cutoff);
            if (f.dates.length < 2) return;
            const card = document.createElement('div');
            card.className = 'progress-card';
            const cid = `wprog-${code}-${months}`;
            card.innerHTML = `<h3>${escapeHtml(ex.code)} — ${escapeHtml(ex.name)} <span style="color:#888;font-weight:400;font-size:0.75rem;">(kg)</span></h3>
                              <canvas id="${cid}" height="160"></canvas>`;
            weightGrid.appendChild(card);
            chartInstances.push(new Chart(document.getElementById(cid), {
                type: 'line',
                data: { datasets: [
                    { label: 'Weight (kg)', data: toXY(f.dates, f.values), borderColor: '#f39c12',
                      backgroundColor: 'rgba(243,156,18,0.15)', fill: true, tension: 0.3,
                      pointRadius: 3, pointHoverRadius: 6, borderWidth: 2 },
                    { label: 'Trend', data: toXY(f.dates, makeTrend(f.values, 4)), borderColor: '#00d4ff',
                      borderDash: [5, 3], pointRadius: 0, borderWidth: 1.5, fill: false }
                ]},
                options: { responsive: true,
                    scales: { x: xScaleOpts, y: { grid: { color: '#222' }, beginAtZero: false } },
                    plugins: { legend: { display: false } } }
            }));
        });
        if (weightGrid.children.length > 0) document.getElementById('weightProgressSection').style.display = '';

        // --- Volume Charts (Active & Dormant) ---
        const activeGrid = document.getElementById('activeProgressGrid');
        const dormantGrid = document.getElementById('dormantProgressGrid');
        const allCodes = Object.keys(progressData);
        const activeCodes = allCodes.filter(c => _daysSince(c) < DORMANT_DAYS).sort((a, b) => _daysSince(b) - _daysSince(a));
        const dormantCodes = allCodes.filter(c => _daysSince(c) >= DORMANT_DAYS).sort((a, b) => _daysSince(b) - _daysSince(a));

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

        // No-chart note
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

    // Initial render (3 months)
    renderAll(3);

    // Button handlers
    document.querySelectorAll('#progressRangeBtns .range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#progressRangeBtns .range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderAll(parseInt(btn.dataset.months));
        });
    });
}

function scrollContainersToEnd() {
    document.querySelectorAll('.heatmap-container, .timeline-container').forEach(el => {
        el.scrollLeft = el.scrollWidth;
    });
}
