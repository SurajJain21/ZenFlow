/* =========================================================
   charts.js - draws all Chart.js charts.
   Flask sends real database values in window.chartData.
   A chart is drawn only if its <canvas> exists on the page.
   ========================================================= */

(function () {
    if (!window.chartData || typeof Chart === "undefined") return;

    const data = window.chartData;
    const colors = {
        water: "#0891b2",
        sleep: "#7c3aed",
        activity: "#16a34a",
        habit: "#ea8a00",
        goal: "#1e2a32",
    };

    Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
    Chart.defaults.color = "#6b7a85";

    // Common options for every bar chart
    function baseOptions(unit, max) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y} ${unit}`,
                    },
                },
            },
            scales: {
                y: { beginAtZero: true, max: max, grid: { color: "#edf1f0" } },
                x: { grid: { display: false } },
            },
        };
    }

    // A flat line showing the goal on every day
    function goalLine(label, value) {
        return {
            type: "line",
            label: label,
            data: data.labels.map(() => value),
            borderColor: colors.goal,
            borderDash: [6, 6],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
        };
    }

    function bars(label, values, color) {
        return {
            type: "bar",
            label: label,
            data: values,
            backgroundColor: color,
            borderRadius: 8,
            maxBarThickness: 38,
        };
    }

    // 1. Weekly water vs goal
    const waterCanvas = document.getElementById("waterChart");
    if (waterCanvas) {
        new Chart(waterCanvas, {
            data: {
                labels: data.labels,
                datasets: [bars("Water (ml)", data.water, colors.water), goalLine("Goal", data.water_goal)],
            },
            options: baseOptions("ml"),
        });
    }

    // 2. Weekly sleep vs target (+ average)
    const sleepCanvas = document.getElementById("sleepChart");
    if (sleepCanvas) {
        const sets = [bars("Sleep (hours)", data.sleep, colors.sleep), goalLine("Target", data.sleep_goal)];
        if (data.sleep_avg) {
            const avg = goalLine("Average", data.sleep_avg);
            avg.borderColor = colors.habit;
            sets.push(avg);
        }
        new Chart(sleepCanvas, { data: { labels: data.labels, datasets: sets }, options: baseOptions("h") });
    }

    // 3. Weekly activity minutes
    const activityCanvas = document.getElementById("activityChart");
    if (activityCanvas) {
        new Chart(activityCanvas, {
            data: { labels: data.labels, datasets: [bars("Activity (min)", data.activity, colors.activity)] },
            options: baseOptions("min"),
        });
    }

    // 4. Daily habit completion %
    const habitCanvas = document.getElementById("habitChart");
    if (habitCanvas) {
        new Chart(habitCanvas, {
            data: { labels: data.labels, datasets: [bars("Habits completed (%)", data.habits_percent, colors.habit)] },
            options: baseOptions("%", 100),
        });
    }

    // 5. Activity type summary (doughnut)
    const typeCanvas = document.getElementById("activityTypeChart");
    if (typeCanvas && data.type_labels && data.type_labels.length) {
        new Chart(typeCanvas, {
            type: "doughnut",
            data: {
                labels: data.type_labels,
                datasets: [{
                    data: data.type_minutes,
                    backgroundColor: ["#16a34a", "#0891b2", "#7c3aed", "#ea8a00", "#0f766e", "#e11d48", "#64748b"],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "65%",
                plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } },
            },
        });
    }
})();
