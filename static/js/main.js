/* =========================================================
   main.js - small helpers for forms and messages
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    // 1. Bootstrap form validation: stop empty / invalid forms from submitting
    document.querySelectorAll("form.needs-validation").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add("was-validated");
        });
    });

    // 2. Ask "are you sure?" before deleting anything
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    // 3. Hide success / info messages automatically after 4 seconds
    document.querySelectorAll(".alert-success, .alert-info").forEach(function (alert) {
        setTimeout(function () {
            if (window.bootstrap) {
                bootstrap.Alert.getOrCreateInstance(alert).close();
            }
        }, 4000);
    });

    // 4. Sleep page: show the calculated sleep duration while typing
    const bed = document.getElementById("bedtime");
    const wake = document.getElementById("wakeup_time");
    const preview = document.getElementById("sleepPreview");
    if (bed && wake && preview) {
        function updatePreview() {
            if (!bed.value || !wake.value) {
                preview.textContent = "—";
                return;
            }
            const [bh, bm] = bed.value.split(":").map(Number);
            const [wh, wm] = wake.value.split(":").map(Number);
            let minutes = (wh * 60 + wm) - (bh * 60 + bm);
            if (minutes <= 0) minutes += 24 * 60;   // slept past midnight
            preview.textContent = Math.floor(minutes / 60) + "h " + (minutes % 60) + "m";
        }
        bed.addEventListener("input", updatePreview);
        wake.addEventListener("input", updatePreview);
        updatePreview();
    }
});
