(function () {
  "use strict";

  const overlayEl = document.getElementById("dispatch-overlay");
  const listEl = document.getElementById("dispatch-rules-list");
  const gearBtn = document.getElementById("dispatch-gear");
  if (!overlayEl || !listEl || !gearBtn) {
    return;
  }

  const feedbackEl = document.getElementById("dispatch-rules-feedback");
  const configPathEl = document.getElementById("dispatch-config-path");
  const closeBtn = overlayEl.querySelector(".dispatch-close");
  const refreshBtn = overlayEl.querySelector(".dispatch-refresh");

  const REFRESH_INTERVAL_MS = 30000;
  let refreshTimer = null;

  const weekdayLabels = ["M", "T", "W", "T", "F", "S", "S"];
  const weekdayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const setFeedback = (type, message) => {
    if (!feedbackEl) {
      return;
    }
    feedbackEl.textContent = message;
    feedbackEl.classList.remove("is-success", "is-error");
    if (type === "success") {
      feedbackEl.classList.add("is-success");
    } else if (type === "error") {
      feedbackEl.classList.add("is-error");
    }
  };

  const clearFeedback = () => {
    if (!feedbackEl) {
      return;
    }
    feedbackEl.textContent = "";
    feedbackEl.classList.remove("is-success", "is-error");
  };

  const formatJobName = (name) => {
    if (!name) {
      return "";
    }
    return name
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  };

  const formatWeekdays = (weekdays) => {
    if (!Array.isArray(weekdays) || weekdays.length === 0) {
      return "";
    }
    const sorted = [...weekdays].sort();
    return sorted.map((day) => weekdayNames[day]).join(", ");
  };

  const buildWeekdayPicker = (weekdays, onDayClick) => {
    const container = document.createElement("div");
    container.className = "weekday-picker";
    container.setAttribute("role", "group");
    container.setAttribute("aria-label", "Weekdays");

    for (let day = 0; day < 7; day += 1) {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "weekday-pill";
      pill.textContent = weekdayLabels[day];
      pill.setAttribute("title", weekdayNames[day]);
      pill.setAttribute("aria-pressed", "false");
      pill.setAttribute("data-day", day);

      if (weekdays && weekdays.includes(day)) {
        pill.classList.add("is-active");
        pill.setAttribute("aria-pressed", "true");
      }

      pill.addEventListener("click", (event) => {
        event.stopPropagation(); // Prevent event from bubbling up to document
        onDayClick(day);
      });

      container.appendChild(pill);
    }

    return container;
  };

  const renderRules = (data) => {
    listEl.innerHTML = "";

    if (!data || !Array.isArray(data.rules) || data.rules.length === 0) {
      listEl.innerHTML = '<div class="dispatch-rules-empty">No dispatch rules found.</div>';
      return;
    }

    if (configPathEl && data.config_path) {
      configPathEl.textContent = data.config_path;
    }

    const timezone = data.timezone || "Asia/Taipei";

    data.rules.forEach((rule) => {
      const card = document.createElement("div");
      card.className = "dispatch-rule-card";

      const header = document.createElement("div");
      header.className = "dispatch-rule-header";

      const titleWrap = document.createElement("div");
      const title = document.createElement("h4");
      title.className = "dispatch-rule-title";
      title.textContent = formatJobName(rule.name);

      const meta = document.createElement("p");
      meta.className = "dispatch-rule-meta";
      if (rule.weekdays_label === "daily" || rule.weekdays.length === 7) {
        meta.textContent = "Runs daily";
      } else {
        const daysText = formatWeekdays(rule.weekdays);
        meta.textContent = daysText ? `Runs on ${daysText}` : "Schedule locked";
      }

      titleWrap.appendChild(title);
      titleWrap.appendChild(meta);

      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "dispatch-save-btn";
      saveBtn.textContent = "Save";
      saveBtn.disabled = true;

      header.appendChild(titleWrap);
      header.appendChild(saveBtn);

      const body = document.createElement("div");
      body.className = "dispatch-rule-body";

      const timeField = document.createElement("div");
      timeField.className = "dispatch-field";
      const timeLabel = document.createElement("label");
      timeLabel.textContent = "Time";
      timeLabel.setAttribute("for", `dispatch-time-${rule.name}`);
      const timeInput = document.createElement("input");
      timeInput.type = "time";
      timeInput.id = `dispatch-time-${rule.name}`;
      timeInput.value = rule.time;
      timeInput.step = "60";
      timeInput.className = "dispatch-time-input";
      const timeHint = document.createElement("small");
      timeHint.textContent = timezone;

      timeField.appendChild(timeLabel);
      timeField.appendChild(timeInput);
      timeField.appendChild(timeHint);

      const weekdayField = document.createElement("div");
      weekdayField.className = "dispatch-field";
      const weekdayLabel = document.createElement("label");
      weekdayLabel.textContent = "Weekdays";
      const selectedDays = [...rule.weekdays];
      
      // Create a single click handler that will work for all re-renders
      const handleDayClick = (day) => {
        const index = selectedDays.indexOf(day);
        if (index > -1) {
          selectedDays.splice(index, 1);
        } else {
          selectedDays.push(day);
          selectedDays.sort();
        }
        
        // Update existing DOM elements instead of replacing
        const pills = weekdayPicker.querySelectorAll('.weekday-pill');
        pills.forEach((pill, i) => {
          if (selectedDays.includes(i)) {
            pill.classList.add('is-active');
            pill.setAttribute('aria-pressed', 'true');
          } else {
            pill.classList.remove('is-active');
            pill.setAttribute('aria-pressed', 'false');
          }
        });
        
        updateSaveState();
      };
      
      const weekdayPicker = buildWeekdayPicker(selectedDays, handleDayClick);
      const weekdayHint = document.createElement("small");
      weekdayHint.textContent = "Select days to run.";

      weekdayField.appendChild(weekdayLabel);
      weekdayField.appendChild(weekdayPicker);
      weekdayField.appendChild(weekdayHint);

      body.appendChild(timeField);
      body.appendChild(weekdayField);

      const updateSaveState = () => {
        const timeDirty = timeInput.value !== rule.time;
        
        // Check if days are dirty - use JSON.stringify to compare sorted arrays
        const daysDirty = JSON.stringify([...selectedDays].sort()) !== JSON.stringify([...rule.weekdays].sort());
        
        const isDirty = timeDirty || daysDirty;
        saveBtn.disabled = !isDirty;
        card.classList.toggle("is-dirty", isDirty);
      };

      timeInput.addEventListener("input", updateSaveState);

      saveBtn.addEventListener("click", async () => {
        const newTime = timeInput.value;
        const newDays = selectedDays.length === 7 ? ["daily"] : [...selectedDays].sort();

        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";

        try {
          const payload = {};
          if (newTime !== rule.time) {
            payload.time = newTime;
          }
          if (JSON.stringify(newDays) !== JSON.stringify(rule.weekdays.sort())) {
            payload.days = newDays;
          }

          const response = await fetch(`/api/dispatch-rules/${encodeURIComponent(rule.name)}`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
          });

          if (!response.ok) {
            let errorMessage = "Failed to update dispatch rule.";
            try {
              const errorData = await response.json();
              if (errorData && errorData.detail) {
                errorMessage = errorData.detail;
              }
            } catch (err) {
              // ignore parse errors
            }
            throw new Error(errorMessage);
          }

          const updated = await response.json();
          rule.time = updated.time || newTime;
          rule.weekdays = updated.days || newDays;
          timeInput.value = rule.time;
          setFeedback("success", `${formatJobName(rule.name)} updated.`);
          updateSaveState();
        } catch (error) {
          setFeedback("error", error.message || "Failed to update dispatch rule.");
        } finally {
          saveBtn.textContent = "Save";
          updateSaveState();
        }
      });

      card.appendChild(header);
      card.appendChild(body);
      listEl.appendChild(card);
    });
  };

  const loadRules = async () => {
    try {
      const response = await fetch("/api/dispatch-rules");
      if (!response.ok) {
        throw new Error("Failed to load dispatch rules.");
      }
      const data = await response.json();
      renderRules(data);
    } catch (error) {
      listEl.innerHTML = '<div class="dispatch-rules-empty">Unable to load dispatch rules.</div>';
      setFeedback("error", error.message || "Unable to load dispatch rules.");
    }
  };

  const positionOverlay = () => {
    const rect = gearBtn.getBoundingClientRect();
    const center = overlayEl.querySelector(".dispatch-center");
    if (!center) {
      return;
    }

    overlayEl.style.top = "-1000px";
    overlayEl.hidden = false;

    const panelWidth = center.offsetWidth;
    overlayEl.style.top = `${rect.bottom + 4}px`;
    overlayEl.style.left = `${rect.right - panelWidth}px`;
  };

  const startPolling = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(() => {
      if (!overlayEl.hidden) {
        loadRules();
      }
    }, REFRESH_INTERVAL_MS);
  };

  const stopPolling = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  };

  const openOverlay = () => {
    positionOverlay();
    clearFeedback();
    loadRules();
    startPolling();
  };

  const closeOverlay = () => {
    overlayEl.hidden = true;
    stopPolling();
  };

  const toggleOverlay = () => {
    if (overlayEl.hidden) {
      openOverlay();
    } else {
      closeOverlay();
    }
  };

  gearBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleOverlay();
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", (event) => {
      event.preventDefault();
      closeOverlay();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", (event) => {
      event.preventDefault();
      loadRules();
    });
  }

  document.addEventListener("click", (event) => {
    if (overlayEl.hidden) {
      return;
    }
    const target = event.target;
    if (overlayEl.contains(target) || gearBtn.contains(target)) {
      return;
    }
    closeOverlay();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlayEl.hidden) {
      closeOverlay();
    }
  });

  window.addEventListener("resize", () => {
    if (!overlayEl.hidden) {
      positionOverlay();
    }
  });
})();