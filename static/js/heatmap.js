/* Heatmap, Exercise Timeline, and Density Timeline rendering */

function renderHeatmap(dailyCounts, dailyExercises) {
    const container = document.getElementById('heatmap');
    const monthsDiv = document.getElementById('heatmapMonths');
    const today = new Date();
    const startDate = new Date(today);
    startDate.setFullYear(startDate.getFullYear() - 1);
    startDate.setDate(startDate.getDate() - ((startDate.getDay() + 6) % 7));

    const maxCount = Math.max(1, ...Object.values(dailyCounts));
    const colors = ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353'];

    function getColor(count) {
        if (!count) return colors[0];
        const idx = Math.min(Math.ceil(count / maxCount * 4), 4);
        return colors[idx];
    }

    let currentMonth = -1;
    let weekCount = 0;
    const d = new Date(startDate);
    while (d <= today) {
        const weekDiv = document.createElement('div');
        weekDiv.className = 'heatmap-week';

        for (let dow = 0; dow < 7; dow++) {
            const dayDiv = document.createElement('div');
            dayDiv.className = 'heatmap-day';
            if (d <= today) {
                const key = d.toISOString().split('T')[0];
                const count = dailyCounts[key] || 0;
                dayDiv.style.background = getColor(count);
                const exList = dailyExercises[key] || [];
                dayDiv.title = exList.length ? `${key}:\n${exList.join('\n')}` : `${key}: Rest day`;
            } else {
                dayDiv.style.background = 'transparent';
            }
            weekDiv.appendChild(dayDiv);
            d.setDate(d.getDate() + 1);
        }

        container.appendChild(weekDiv);
        weekCount++;
    }

    const md = new Date(startDate);
    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    let lastMonth = -1;
    let weekIdx = 0;
    const md2 = new Date(startDate);
    while (md2 <= today) {
        const m = md2.getMonth();
        if (m !== lastMonth) {
            const span = document.createElement('span');
            span.className = 'heatmap-month';
            span.textContent = monthNames[m];
            span.style.marginLeft = (weekIdx * 16) + 'px';
            span.style.position = 'absolute';
            monthsDiv.appendChild(span);
            lastMonth = m;
        }
        md2.setDate(md2.getDate() + 7);
        weekIdx++;
    }
    monthsDiv.style.position = 'relative';
    monthsDiv.style.height = '16px';
}

function renderTimeline(timelineData, exercises) {
    const container = document.getElementById('timeline');
    const today = new Date();
    let earliest = today;
    Object.values(timelineData).forEach(dates => {
        dates.forEach(d => {
            const dt = new Date(d);
            if (dt < earliest) earliest = dt;
        });
    });
    const startDate = new Date(earliest);
    startDate.setDate(1);

    const totalDays = Math.ceil((today - startDate) / 86400000);

    const headerRow = document.createElement('div');
    headerRow.className = 'timeline-row';
    const headerLabel = document.createElement('div');
    headerLabel.className = 'timeline-label';
    headerLabel.style.color = '#555';
    headerLabel.textContent = '';
    headerRow.appendChild(headerLabel);
    const headerDots = document.createElement('div');
    headerDots.className = 'timeline-dots';
    headerDots.style.position = 'relative';
    for (let i = 0; i < totalDays; i++) {
        const d = new Date(startDate);
        d.setDate(d.getDate() + i);
        const dot = document.createElement('div');
        dot.className = 'timeline-dot';
        dot.style.background = 'transparent';
        dot.style.height = '16px';
        if (d.getDate() === 1 && [0, 3, 6, 9].includes(d.getMonth())) {
            dot.classList.add('quarter-line');
            dot.style.position = 'relative';
            const lbl = document.createElement('span');
            lbl.style.cssText = 'position:absolute;top:-2px;left:2px;font-size:0.65rem;color:#888;white-space:nowrap;';
            const qNames = ['Q1','Q2','Q2','Q2','Q3','Q3','Q3','Q4','Q4','Q4','Q1','Q1'];
            const monthNames = ['Jan','Apr','Jul','Oct'];
            const mIdx = [0,3,6,9].indexOf(d.getMonth());
            lbl.textContent = monthNames[mIdx] + ' ' + d.getFullYear().toString().slice(2);
            dot.appendChild(lbl);
        }
        headerDots.appendChild(dot);
    }
    headerRow.appendChild(headerDots);
    container.appendChild(headerRow);

    const byCategory = {};
    const dormantByCategory = {};
    const dormantThreshold = 90;
    exercises.forEach(ex => {
        if (!timelineData[ex.code]) return;
        const dates = timelineData[ex.code];
        const lastDate = new Date(dates[dates.length - 1]);
        const daysSinceLast = Math.ceil((today - lastDate) / 86400000);
        const isDormant = daysSinceLast > dormantThreshold;
        const target = isDormant ? dormantByCategory : byCategory;
        if (!target[ex.category]) target[ex.category] = [];
        target[ex.category].push(ex);
    });

    const bodyAreaOrder = ['back', 'chest', 'arms', 'legs', 'core'];

    function renderExRow(ex, cat, container, dimmed) {
        const dates = new Set(timelineData[ex.code] || []);
        const row = document.createElement('div');
        row.className = 'timeline-row';
        const label = document.createElement('div');
        label.className = 'timeline-label';
        if (dimmed) label.style.opacity = '0.5';
        label.textContent = ex.code + ' ΓÇö ' + ex.name;
        label.title = ex.name;
        row.appendChild(label);
        const dotsDiv = document.createElement('div');
        dotsDiv.className = 'timeline-dots';
        for (let i = 0; i < totalDays; i++) {
            const d = new Date(startDate);
            d.setDate(d.getDate() + i);
            const key = d.toISOString().split('T')[0];
            const dot = document.createElement('div');
            dot.className = 'timeline-dot';
            dot.style.background = dates.has(key) ? catColors[cat] : (dimmed ? '#1a1a1a' : '#222');
            if (d.getDate() === 1 && [0, 3, 6, 9].includes(d.getMonth())) {
                dot.classList.add('quarter-line');
            }
            dotsDiv.appendChild(dot);
        }
        row.appendChild(dotsDiv);
        container.appendChild(row);
    }

    categoryOrder.forEach(cat => {
        const exList = byCategory[cat];
        if (!exList || exList.length === 0) return;

        const header = document.createElement('div');
        header.className = 'timeline-category-header';
        header.style.color = catColors[cat];
        header.textContent = cat.toUpperCase();
        container.appendChild(header);

        if (cat === 'strength') {
            const byArea = {};
            const noArea = [];
            exList.forEach(ex => {
                const area = ex.body_area;
                if (area) {
                    if (!byArea[area]) byArea[area] = [];
                    byArea[area].push(ex);
                } else {
                    noArea.push(ex);
                }
            });
            bodyAreaOrder.forEach(area => {
                if (!byArea[area] || byArea[area].length === 0) return;
                const subHeader = document.createElement('div');
                subHeader.style.cssText = 'font-size:0.65rem; color:#666; padding:3px 0 1px 8px; text-transform:uppercase; letter-spacing:1px;';
                subHeader.textContent = area;
                container.appendChild(subHeader);
                byArea[area].forEach(ex => renderExRow(ex, cat, container, false));
            });
            noArea.forEach(ex => renderExRow(ex, cat, container, false));
        } else {
            exList.forEach(ex => renderExRow(ex, cat, container, false));
        }
    });

    const hasDormant = Object.values(dormantByCategory).some(l => l.length > 0);
    if (hasDormant) {
        const sep = document.createElement('div');
        sep.style.cssText = 'border-top:2px solid #555; margin:12px 0 8px 0; position:relative;';
        const sepLabel = document.createElement('span');
        sepLabel.style.cssText = 'position:absolute; top:-10px; left:8px; background:#0a0a23; padding:0 8px; color:#888; font-size:0.75rem;';
        sepLabel.textContent = 'DORMANT (3+ months inactive)';
        sep.appendChild(sepLabel);
        container.appendChild(sep);

        categoryOrder.forEach(cat => {
            const exList = dormantByCategory[cat];
            if (!exList || exList.length === 0) return;
            exList.forEach(ex => renderExRow(ex, cat, container, true));
        });
    }
}

function renderDensityTimeline(timelineData, exercises) {
    const container = document.getElementById('densityTimeline');
    const today = new Date();
    let earliest = today;
    Object.values(timelineData).forEach(dates => {
        dates.forEach(d => {
            const dt = new Date(d);
            if (dt < earliest) earliest = dt;
        });
    });
    const startDate = new Date(earliest);
    startDate.setDate(1);
    const totalDays = Math.ceil((today - startDate) / 86400000);
    const WINDOW = 14;

    const headerRow = document.createElement('div');
    headerRow.className = 'timeline-row';
    const headerLabel = document.createElement('div');
    headerLabel.className = 'timeline-label';
    headerRow.appendChild(headerLabel);
    const headerDots = document.createElement('div');
    headerDots.className = 'timeline-dots';
    for (let i = 0; i < totalDays; i++) {
        const d = new Date(startDate);
        d.setDate(d.getDate() + i);
        const dot = document.createElement('div');
        dot.className = 'timeline-dot';
        dot.style.background = 'transparent';
        dot.style.height = '16px';
        if (d.getDate() === 1 && [0, 3, 6, 9].includes(d.getMonth())) {
            dot.classList.add('quarter-line');
            dot.style.position = 'relative';
            const lbl = document.createElement('span');
            lbl.style.cssText = 'position:absolute;top:-2px;left:2px;font-size:0.65rem;color:#888;white-space:nowrap;';
            const monthNames = ['Jan','Apr','Jul','Oct'];
            const mIdx = [0,3,6,9].indexOf(d.getMonth());
            lbl.textContent = monthNames[mIdx] + ' ' + d.getFullYear().toString().slice(2);
            dot.appendChild(lbl);
        }
        headerDots.appendChild(dot);
    }
    headerRow.appendChild(headerDots);
    container.appendChild(headerRow);

    const byCategory = {};
    exercises.forEach(ex => {
        if (!timelineData[ex.code]) return;
        if (!byCategory[ex.category]) byCategory[ex.category] = [];
        byCategory[ex.category].push(ex);
    });

    const bodyAreaOrder2 = ['back', 'chest', 'arms', 'legs', 'core'];

    function renderDensityRow(ex, cat) {
        const dateSet = new Set(timelineData[ex.code] || []);
        const row = document.createElement('div');
        row.className = 'timeline-row';

        const label = document.createElement('div');
        label.className = 'timeline-label';
        label.textContent = ex.code + ' ΓÇö ' + ex.name;
        label.title = ex.name;
        row.appendChild(label);

        const dotsDiv = document.createElement('div');
        dotsDiv.className = 'timeline-dots';

        const allDates = [];
        for (let i = 0; i < totalDays; i++) {
            const d = new Date(startDate);
            d.setDate(d.getDate() + i);
            allDates.push(d.toISOString().split('T')[0]);
        }

        let windowCount = 0;
        const windowQueue = [];
        for (let i = 0; i < totalDays; i++) {
            const key = allDates[i];
            const hit = dateSet.has(key) ? 1 : 0;
            windowQueue.push(hit);
            windowCount += hit;
            if (windowQueue.length > WINDOW) {
                windowCount -= windowQueue.shift();
            }

            const dot = document.createElement('div');
            dot.className = 'timeline-dot';

            const intensity = Math.min(windowCount / 7, 1);
            if (intensity === 0) {
                dot.style.background = '#222';
            } else {
                const baseColor = catColors[cat];
                const r = parseInt(baseColor.slice(1,3), 16);
                const g = parseInt(baseColor.slice(3,5), 16);
                const b = parseInt(baseColor.slice(5,7), 16);
                const alpha = 0.2 + intensity * 0.8;
                dot.style.background = `rgba(${r},${g},${b},${alpha})`;
            }
            dot.title = `${key}: ${windowCount} in last ${WINDOW} days`;

            if (new Date(key).getDate() === 1 && [0, 3, 6, 9].includes(new Date(key).getMonth())) {
                dot.classList.add('quarter-line');
            }
            dotsDiv.appendChild(dot);
        }

        row.appendChild(dotsDiv);
        container.appendChild(row);
    }

    categoryOrder.forEach(cat => {
        const exList = byCategory[cat];
        if (!exList || exList.length === 0) return;

        const header = document.createElement('div');
        header.className = 'timeline-category-header';
        header.style.color = catColors[cat];
        header.textContent = cat.toUpperCase();
        container.appendChild(header);

        if (cat === 'strength') {
            const byArea = {};
            const noArea = [];
            exList.forEach(ex => {
                const area = ex.body_area;
                if (area) {
                    if (!byArea[area]) byArea[area] = [];
                    byArea[area].push(ex);
                } else {
                    noArea.push(ex);
                }
            });
            bodyAreaOrder2.forEach(area => {
                if (!byArea[area] || byArea[area].length === 0) return;
                const subHeader = document.createElement('div');
                subHeader.style.cssText = 'font-size:0.65rem; color:#666; padding:3px 0 1px 8px; text-transform:uppercase; letter-spacing:1px;';
                subHeader.textContent = area;
                container.appendChild(subHeader);
                byArea[area].forEach(ex => renderDensityRow(ex, cat));
            });
            noArea.forEach(ex => renderDensityRow(ex, cat));
        } else {
            exList.forEach(ex => renderDensityRow(ex, cat));
        }
    });
}
