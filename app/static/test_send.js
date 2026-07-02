(function () {
  "use strict";

  const overlayEl = document.getElementById("test-send-overlay");
  const sourceSelectEl = document.getElementById("test-send-source");
  const sendBtn = document.getElementById("test-send-button");
  const feedbackEl = document.getElementById("test-send-feedback");
  const headerBtn = document.getElementById("test-send-btn");
  const closeButtons = overlayEl ? overlayEl.querySelectorAll(".test-send-close") : [];

  if (!overlayEl || !sourceSelectEl || !sendBtn || !headerBtn) {
    return;
  }

  let feedbackTimeout = null;

  const setFeedback = (type, message) => {
    feedbackEl.textContent = message;
    feedbackEl.classList.remove("is-success", "is-error");
    if (type === "success") {
      feedbackEl.classList.add("is-success");
    } else if (type === "error") {
      feedbackEl.classList.add("is-error");
    }

    if (feedbackTimeout) {
      clearTimeout(feedbackTimeout);
    }

    if (type === "success") {
      feedbackTimeout = setTimeout(() => {
        clearFeedback();
      }, 5000);
    }
  };

  const clearFeedback = () => {
    feedbackEl.textContent = "";
    feedbackEl.classList.remove("is-success", "is-error");
    if (feedbackTimeout) {
      clearTimeout(feedbackTimeout);
      feedbackTimeout = null;
    }
  };

  const loadJobs = async () => {
    try {
      const response = await fetch("/api/dispatch-rules");
      if (!response.ok) {
        throw new Error("Failed to load jobs");
      }
      const data = await response.json();

      // Extract daily send jobs (filter out summary jobs)
      const dailySendJobs = [];
      if (data.rules && Array.isArray(data.rules)) {
        data.rules.forEach(rule => {
          if (rule.name && rule.name.includes("daily-send")) {
            dailySendJobs.push(rule.name);
          }
        });
      }

      // Populate dropdown with job names
      sourceSelectEl.innerHTML = '<option value="">-- Select a job --</option>';
      dailySendJobs.sort().forEach(jobName => {
        const option = document.createElement("option");
        option.value = jobName;
        // Format job name for display (e.g., "morning-revival-daily-send" -> "Morning Revival")
        const displayName = jobName
          .replace("-daily-send", "")
          .split("-")
          .map(w => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" ");
        option.textContent = displayName;
        sourceSelectEl.appendChild(option);
      });
    } catch (error) {
      console.error("Failed to load jobs:", error);
      // Fallback: add known jobs
      const fallbackJobs = ["morning-revival-daily-send", "bible-journey-daily-send", "stmn1-bible-journey-daily-send"];
      sourceSelectEl.innerHTML = '<option value="">-- Select a job --</option>';
      fallbackJobs.forEach(jobName => {
        const option = document.createElement("option");
        option.value = jobName;
        const displayName = jobName
          .replace("-daily-send", "")
          .split("-")
          .map(w => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" ");
        option.textContent = displayName;
        sourceSelectEl.appendChild(option);
      });
    }
  };

  const openOverlay = () => {
    // Hide all other overlays
    if (window.hideAllOverlaysExcept) {
      window.hideAllOverlaysExcept('test-send-overlay');
    }

    overlayEl.hidden = false;
    clearFeedback();
    loadJobs();
  };

  const closeOverlay = () => {
    overlayEl.hidden = true;
  };

  const toggleOverlay = () => {
    if (overlayEl.hidden) {
      openOverlay();
    } else {
      closeOverlay();
    }
  };

  sendBtn.addEventListener("click", async () => {
    const jobName = sourceSelectEl.value.trim();
    if (!jobName) {
      setFeedback("error", "Please select a job");
      return;
    }

    sendBtn.disabled = true;
    const originalText = sendBtn.textContent;
    sendBtn.textContent = "Running...";

    try {
      const response = await fetch("/api/test-send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_name: jobName }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to run test job");
      }

      setFeedback("success", data.message);
      sourceSelectEl.value = "";
    } catch (error) {
      setFeedback("error", error.message || "Failed to run test job");
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = originalText;
    }
  });

  headerBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleOverlay();
  });

  closeButtons.forEach(btn => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      closeOverlay();
    });
  });

  document.addEventListener("click", (event) => {
    if (overlayEl.hidden) {
      return;
    }
    const target = event.target;
    if (overlayEl.contains(target) || headerBtn.contains(target)) {
      return;
    }
    closeOverlay();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlayEl.hidden) {
      closeOverlay();
    }
  });
})();
