(function () {
  "use strict";

  const DAY_MS = 24 * 60 * 60 * 1000;

  const parseISODate = (value) => {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day));
  };

  const formatISODate = (dateObj) => {
    const year = dateObj.getUTCFullYear();
    const month = String(dateObj.getUTCMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getUTCDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const addDays = (dateObj, days) => {
    return new Date(dateObj.getTime() + days * DAY_MS);
  };

  const differenceInDays = (a, b) => {
    return Math.round((b.getTime() - a.getTime()) / DAY_MS);
  };

  class CalendarApp {
    constructor(config) {
      this.config = config || {};
      this.scrollEl = document.getElementById("calendar-scroll");
      this.flashContainer = document.getElementById("flash-messages");
      this.monthYearEl = document.getElementById("month-year");
      this.batchToolbarEl = document.getElementById("batch-toolbar");
      this.batchEditBtn = document.getElementById("batch-edit-btn");
      this.selectionCountEl = document.getElementById("selection-count");
      this.popoverEl = document.getElementById("calendar-popover");
      this.popoverForm = document.getElementById("popover-form");
      this.popoverDateInput = document.getElementById("popover-date");
      this.selectorInput = document.getElementById("popover-selector");
      this.statusInput = document.getElementById("popover-status");
      this.notesInput = document.getElementById("popover-notes");
      this.overrideInput = document.getElementById("popover-override");
      this.popoverDateLabel = document.getElementById("popover-date-label");
      this.popoverSentMeta = document.getElementById("popover-sent-meta");
      this.dateAdjustOverlay = document.getElementById("date-adjust-overlay");
      this.dateAdjustForm = document.getElementById("date-adjust-form");
      this.dateAdjustInput = document.getElementById("date-adjust-input");
      this.batchEditOverlay = document.getElementById("batch-edit-overlay");
      this.batchEditForm = document.getElementById("batch-edit-form");
      this.batchSelectorInput = document.getElementById("batch-selector");
      this.batchStatusInput = document.getElementById("batch-status");
      this.batchNotesInput = document.getElementById("batch-notes");
      this.batchOverrideInput = document.getElementById("batch-override");
      this.selection = new Set();
      this.lastSelectedDate = null;
      this.dragOriginDate = null;
      this.entriesIndex = new Map();
      this.monthEntries = new Map();
      this.visibleMonths = [];
      this.focusedMonthKey = null;
      this.currentYear = null;
      this.currentMonth = null;
      this.activePopoverAnchor = null;
      this.autoScrollTimer = null;
      this.loadingNext = false;
      this.loadingPrev = false;
      this.scrollTicking = false;
      this.maxVisibleMonths = 6;
      this.fullFormatter = new Intl.DateTimeFormat(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      });
      this.monthFormatter = new Intl.DateTimeFormat(undefined, {
        month: "long",
        year: "numeric",
      });
      this.batchUIConfig = null;
    }

    init() {
      if (!this.scrollEl) {
        return;
      }
      this.bindToolbar();
      this.bindPopover();
      this.bindDateAdjustOverlay();
      this.bindBatchEditOverlay();
      this.bindGlobalKeys();
      this.bindScrollBehavior();
      this.bindSessionDetection();
      this.showInitialFlash();

      // Load batch UI config and schedule data
      Promise.all([
        this.loadBatchUIConfig(),
        this.resetToMonth()
      ]).catch((error) => {
        this.showFlash("error", error.message || "Unable to load schedule");
      });
    }

    bindToolbar() {
      const prevBtn = document.getElementById("prev-month");
      const nextBtn = document.getElementById("next-month");
      const todayBtn = document.getElementById("today-month");
      if (prevBtn) {
        prevBtn.addEventListener("click", () => {
          this.shiftMonth(-1);
        });
      }
      if (nextBtn) {
        nextBtn.addEventListener("click", () => {
          this.shiftMonth(1);
        });
      }
      if (todayBtn) {
        todayBtn.addEventListener("click", () => {
          this.resetToMonth();
        });
      }

      // Bind batch edit button
      if (this.batchEditBtn) {
        this.batchEditBtn.addEventListener("click", () => {
          this.showBatchEditOverlay();
        });
      }
    }

    bindPopover() {
      if (!this.popoverForm) {
        return;
      }
      this.popoverForm.addEventListener("submit", (event) => {
        event.preventDefault();
        this.submitPopover();
      });
      const closeButtons = this.popoverEl.querySelectorAll(
        '[data-action="close"]',
      );
      closeButtons.forEach((btn) => {
        btn.addEventListener("click", (event) => {
          event.preventDefault();
          this.closePopover();
        });
      });
      const markSentBtn = this.popoverEl.querySelector(
        '[data-action="mark-sent"]',
      );
      if (markSentBtn) {
        markSentBtn.addEventListener("click", (event) => {
          event.preventDefault();
          if (this.statusInput) {
            this.statusInput.value = "sent";
          }
          this.submitPopover();
        });
      }
      const markSkippedBtn = this.popoverEl.querySelector(
        '[data-action="mark-skipped"]',
      );
      if (markSkippedBtn) {
        markSkippedBtn.addEventListener("click", (event) => {
          event.preventDefault();
          if (this.statusInput) {
            this.statusInput.value = "skipped";
          }
          this.submitPopover();
        });
      }
      const deleteBtn = this.popoverEl.querySelector(
        '[data-action="delete"]',
      );
      if (deleteBtn) {
        deleteBtn.addEventListener("click", (event) => {
          event.preventDefault();
          this.handleDelete();
        });
      }
      document.addEventListener("click", (event) => {
        if (this.popoverEl.hidden) {
          return;
        }
        const target = event.target;
        if (this.popoverEl.contains(target)) {
          return;
        }
        if (
          this.activePopoverAnchor &&
          this.activePopoverAnchor.contains(target)
        ) {
          return;
        }
        this.closePopover();
      });
      window.addEventListener("resize", () => {
        if (!this.popoverEl.hidden && this.activePopoverAnchor) {
          this.positionPopover(this.activePopoverAnchor);
        }
      });
    }

    bindDateAdjustOverlay() {
      if (!this.dateAdjustForm) {
        return;
      }
      this.dateAdjustForm.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!this.selection.size) {
          return;
        }
        const targetDate = this.dateAdjustInput.value;
        if (!targetDate) {
          return;
        }
        this.moveSelection(targetDate).then(() => {
          this.hideDateAdjustOverlay();
        });
      });
      const cancelBtn = this.dateAdjustForm.querySelector(
        '[data-action="cancel"]',
      );
      if (cancelBtn) {
        cancelBtn.addEventListener("click", (event) => {
          event.preventDefault();
          this.hideDateAdjustOverlay();
        });
      }
    }

    bindBatchEditOverlay() {
      const overlay = this.batchEditOverlay;
      const form = this.batchEditForm;
      if (!overlay || !form) {
        return;
      }

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this.submitBatchEdit();
      });

      const cancelButtons = overlay.querySelectorAll('[data-action="cancel"]');
      cancelButtons.forEach((btn) => {
        btn.addEventListener("click", (event) => {
          event.preventDefault();
          this.hideBatchEditOverlay();
        });
      });

      const deleteBtn = overlay.querySelector('[data-action="batch-delete"]');
      if (deleteBtn) {
        deleteBtn.addEventListener("click", (event) => {
          event.preventDefault();
          this.handleBatchDelete();
        });
      }
    }

    bindGlobalKeys() {
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          this.closeAllOverlays();
          return;
        }
        if (
          event.key &&
          event.key.toLowerCase() === "d" &&
          event.shiftKey &&
          !event.metaKey &&
          !event.ctrlKey
        ) {
          if (!this.selection.size) {
            return;
          }
          event.preventDefault();
          this.showDateAdjustOverlay();
        }
      });
    }

    // Centralized overlay management
    closeAllOverlays() {
      this.closePopover();
      this.hideDateAdjustOverlay();
      this.hideBatchEditOverlay();
      this.hideNotificationOverlay();
      this.hideDispatchOverlay();
    }

    // Overlay visibility helpers
    isOverlayVisible(overlayId) {
      const overlay = document.getElementById(overlayId);
      return overlay && !overlay.hidden;
    }

    hideAllOverlaysExcept(exceptId) {
      const overlayIds = [
        'calendar-popover',
        'date-adjust-overlay',
        'batch-edit-overlay',
        'notification-overlay',
        'dispatch-overlay'
      ];

      overlayIds.forEach(id => {
        if (id !== exceptId) {
          const overlay = document.getElementById(id);
          if (overlay && !overlay.hidden) {
            overlay.hidden = true;
          }
        }
      });
    }

    // Notification overlay management
    hideNotificationOverlay() {
      const overlay = document.getElementById('notification-overlay');
      if (overlay) {
        overlay.hidden = true;
      }
    }

    // Dispatch overlay management
    hideDispatchOverlay() {
      const overlay = document.getElementById('dispatch-overlay');
      if (overlay) {
        overlay.hidden = true;
      }
    }

    bindScrollBehavior() {
      if (!this.scrollEl) {
        return;
      }
      this.scrollEl.addEventListener("scroll", () => {
        if (this.scrollTicking) {
          return;
        }
        this.scrollTicking = true;
        window.requestAnimationFrame(() => {
          this.maybeLoadAdjacentMonths();
          this.updateActiveMonthLabel();
          this.scrollTicking = false;
        });
      });
    }

    bindSessionDetection() {
      // Check session when user returns to the tab
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
          this.checkSessionStatus();
        }
      });

      // Check session when window gains focus
      window.addEventListener('focus', () => {
        this.checkSessionStatus();
      });
    }

    async checkSessionStatus() {
      try {
        // Use a lightweight endpoint to check session
        const response = await fetch('/oauth/status', {
          credentials: 'include'
        });

        if (response.status === 401) {
          // Session expired - show interactive countdown
          this.showSessionExpiryFlash();
        }
      } catch (e) {
        // Ignore network errors - user might be offline
        console.debug('Session check failed:', e);
      }
    }

    async resetToMonth(year, month) {
      if (!this.scrollEl) {
        return;
      }
      try {
        this.scrollEl.innerHTML = "";
        this.visibleMonths = [];
        this.entriesIndex.clear();
        this.monthEntries.clear();
        this.selection.clear();
        this.lastSelectedDate = null;
        this.dragOriginDate = null;
        const data = await this.loadMonthData(year, month);
        this.insertMonthSection(data, "append");
        this.scrollEl.scrollTop = 0;
        this.setActiveMonth(data.year, data.month);
        this.updateActiveMonthLabel();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to load schedule");
      }
    }

    async loadMonthData(year, month) {
      let params = "";
      if (typeof year === "number" && typeof month === "number") {
        params = `?year=${year}&month=${month}`;
      }
      const response = await fetch(
        `${window.location.origin}/api/month${params}`,
        {
          credentials: "include",
        },
      );
      if (!response.ok) {
        throw new Error(await this.extractError(response));
      }
      return response.json();
    }

    async ensureMonth(year, month, position) {
      const key = this.monthKey(year, month);
      const existing = this.visibleMonths.find(
        (monthEntry) => monthEntry.key === key,
      );
      if (existing) {
        return existing.el;
      }
      const data = await this.loadMonthData(year, month);
      return this.insertMonthSection(data, position);
    }

    insertMonthSection(data, position = "append") {
      if (!this.scrollEl) {
        return null;
      }
      const section = this.buildMonthSection(data);
      const key = this.monthKey(data.year, data.month);
      if (position === "prepend" && this.visibleMonths.length) {
        const previousScrollHeight = this.scrollEl.scrollHeight;
        this.scrollEl.prepend(section);
        const delta = this.scrollEl.scrollHeight - previousScrollHeight;
        this.scrollEl.scrollTop += delta;
        this.visibleMonths.unshift({
          key,
          year: data.year,
          month: data.month,
          el: section,
        });
      } else if (position === "prepend") {
        this.scrollEl.prepend(section);
        this.visibleMonths.unshift({
          key,
          year: data.year,
          month: data.month,
          el: section,
        });
      } else {
        this.scrollEl.appendChild(section);
        this.visibleMonths.push({
          key,
          year: data.year,
          month: data.month,
          el: section,
        });
      }
      this.registerMonthEntries(key, data.entries);
      this.updateSelectionClasses();
      this.updateActiveMonthLabel();
      return section;
    }

    buildMonthSection(data) {
      const section = document.createElement("section");
      section.className = "calendar-month";
      section.dataset.key = this.monthKey(data.year, data.month);

      const header = document.createElement("header");
      header.className = "calendar-month-header";

      const label = document.createElement("p");
      label.className = "calendar-month-label";
      label.textContent = this.monthFormatter.format(
        new Date(data.year, data.month - 1, 1),
      );
      header.appendChild(label);

      const range = document.createElement("p");
      range.className = "calendar-month-range";
      range.textContent = `${data.month_start} – ${data.month_end}`;
      header.appendChild(range);
      section.appendChild(header);

      const grid = document.createElement("div");
      grid.className = "calendar-grid";
      grid.setAttribute("role", "grid");
      grid.setAttribute("aria-label", label.textContent);
      data.entries.forEach((entry) => {
        grid.appendChild(this.buildDayCell(entry));
      });
      section.appendChild(grid);
      return section;
    }

    registerMonthEntries(key, entries) {
      const dates = [];
      entries.forEach((entry) => {
        this.entriesIndex.set(entry.date, entry);
        dates.push(entry.date);
      });
      this.monthEntries.set(key, dates);
    }

    dropMonthEntries(key) {
      const dates = this.monthEntries.get(key) || [];
      dates.forEach((date) => this.entriesIndex.delete(date));
      this.monthEntries.delete(key);
    }

    monthKey(year, month) {
      return `${year}-${String(month).padStart(2, "0")}`;
    }

    offsetMonth(year, month, delta) {
      const base = new Date(Date.UTC(year, month - 1 + delta, 1));
      return {
        year: base.getUTCFullYear(),
        month: base.getUTCMonth() + 1,
      };
    }

    async shiftMonth(offsetMonths) {
      if (!this.scrollEl) {
        return;
      }
      const baseYear =
        this.currentYear ||
        (this.visibleMonths[0] && this.visibleMonths[0].year);
      const baseMonth =
        this.currentMonth ||
        (this.visibleMonths[0] && this.visibleMonths[0].month);
      if (!baseYear || !baseMonth) {
        await this.resetToMonth();
        return;
      }
      const target = this.offsetMonth(baseYear, baseMonth, offsetMonths);
      const position = offsetMonths > 0 ? "append" : "prepend";
      try {
        await this.ensureMonth(target.year, target.month, position);
        this.scrollToMonth(this.monthKey(target.year, target.month));
        this.setActiveMonth(target.year, target.month);
      } catch (error) {
        this.showFlash("error", error.message || "Unable to load schedule");
      }
    }

    scrollToMonth(key) {
      const target = this.visibleMonths.find((item) => item.key === key);
      if (!target || !this.scrollEl) {
        return;
      }
      target.el.scrollIntoView({
        behavior: "smooth",
        block: "start",
        inline: "nearest",
      });
    }

    maybeLoadAdjacentMonths() {
      if (!this.scrollEl || !this.visibleMonths.length) {
        return;
      }
      const { scrollTop, scrollHeight, clientHeight } = this.scrollEl;
      const buffer = 160;
      if (scrollHeight - (scrollTop + clientHeight) < buffer) {
        this.loadAdjacentMonth(1);
      }
      if (scrollTop < buffer) {
        this.loadAdjacentMonth(-1);
      }
    }

    async loadAdjacentMonth(direction) {
      if (direction > 0 && this.loadingNext) {
        return;
      }
      if (direction < 0 && this.loadingPrev) {
        return;
      }
      const anchor =
        direction > 0
          ? this.visibleMonths[this.visibleMonths.length - 1]
          : this.visibleMonths[0];
      if (!anchor) {
        return;
      }
      const target = this.offsetMonth(anchor.year, anchor.month, direction);
      const key = this.monthKey(target.year, target.month);
      if (this.visibleMonths.some((item) => item.key === key)) {
        return;
      }
      if (direction > 0) {
        this.loadingNext = true;
      } else {
        this.loadingPrev = true;
      }
      try {
        await this.ensureMonth(
          target.year,
          target.month,
          direction > 0 ? "append" : "prepend",
        );
        this.trimVisibleMonths(direction);
      } catch (error) {
        this.showFlash("error", error.message || "Unable to load schedule");
      } finally {
        if (direction > 0) {
          this.loadingNext = false;
        } else {
          this.loadingPrev = false;
        }
      }
    }

    trimVisibleMonths(direction) {
      while (this.visibleMonths.length > this.maxVisibleMonths) {
        const removed =
          direction > 0 ? this.visibleMonths.shift() : this.visibleMonths.pop();
        if (removed) {
          this.dropMonthEntries(removed.key);
          removed.el.remove();
        }
      }
    }

    updateActiveMonthLabel() {
      if (!this.monthYearEl || !this.scrollEl || !this.visibleMonths.length) {
        return;
      }
      const containerRect = this.scrollEl.getBoundingClientRect();
      let closest = null;
      let shortest = Number.POSITIVE_INFINITY;
      this.visibleMonths.forEach((monthEntry) => {
        const rect = monthEntry.el.getBoundingClientRect();
        const distance = Math.abs(rect.top - containerRect.top);
        if (distance < shortest) {
          shortest = distance;
          closest = monthEntry;
        }
      });
      if (closest) {
        const key = closest.key;
        if (this.focusedMonthKey !== key) {
          this.focusedMonthKey = key;
          this.setActiveMonth(closest.year, closest.month);
        }
      }
    }

    setActiveMonth(year, month) {
      this.currentYear = year;
      this.currentMonth = month;
      if (!this.monthYearEl || !year || !month) {
        return;
      }
      const date = new Date(year, month - 1, 1);
      this.monthYearEl.textContent = this.monthFormatter.format(date);
    }

    async refreshFocusedMonth() {
      if (!this.currentYear || !this.currentMonth) {
        await this.resetToMonth();
        return;
      }
      await this.resetToMonth(this.currentYear, this.currentMonth);
    }

    async loadBatchUIConfig() {
      try {
        const response = await fetch(
          `${window.location.origin}/api/batch-edit/config`,
          { credentials: "include" }
        );
        if (!response.ok) {
          throw new Error("Failed to load batch edit configuration");
        }
        const data = await response.json();
        this.batchUIConfig = data.ui_config;
        return data;
      } catch (error) {
        console.error("Error loading batch UI config:", error);
        // Fallback to generic config
        this.batchUIConfig = {
          placeholder: "Enter selectors (comma or newline separated)",
          help_text: "Enter one or more selectors",
          examples: [],
          supports_range: false,
          range_example: null,
        };
      }
    }


    showInitialFlash() {
      if (this.config.message) {
        this.showFlash("success", this.config.message);
      }
      if (this.config.error) {
        this.showFlash("error", this.config.error);
      }
    }

    buildDayCell(entry) {
      const cell = document.createElement("div");
      cell.className = `calendar-day${entry.is_current_month ? "" : " outside-month"}`;
      cell.dataset.date = entry.date;
      cell.setAttribute("role", "gridcell");

      const header = document.createElement("div");
      header.className = "day-header";

      const title = document.createElement("div");
      title.className = "day-label";
      const dayNumber = Number(entry.date.slice(-2));
      title.innerHTML = `<span class="weekday">${entry.weekday_short}</span><span class="day-number">${dayNumber}</span>`;

      const addButton = document.createElement("button");
      addButton.type = "button";
      addButton.className = "day-add";
      addButton.title = `Add schedule for ${entry.date}`;
      addButton.setAttribute("aria-label", `Add schedule for ${entry.date}`);
      addButton.innerHTML = '<span aria-hidden="true">＋</span>';
      addButton.addEventListener("click", (event) => {
        event.stopPropagation();
        this.setSingleSelection(entry.date);
        this.openPopover(entry.date, cell, true);
      });

      header.appendChild(title);
      header.appendChild(addButton);

      const body = document.createElement("div");
      body.className = "day-body";

      if (!entry.is_missing) {
        const chip = document.createElement("div");
        chip.className = "event-chip";
        chip.tabIndex = 0;
        chip.textContent = entry.selector
          ? `${entry.selector} · ${entry.status || "pending"}`
          : "Scheduled";
        chip.draggable = true;
        chip.addEventListener("click", (event) =>
          this.handleEventClick(event, entry, cell),
        );
        chip.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.handleEventClick(event, entry, cell);
          }
        });
        chip.addEventListener("dragstart", (event) =>
          this.handleDragStart(event, entry),
        );
        chip.addEventListener("dragend", () => this.handleDragEnd());
        body.appendChild(chip);
        if (entry.notes) {
          const note = document.createElement("p");
          note.className = "event-note";
          note.textContent = entry.notes;
          body.appendChild(note);
        }

        // Add stacking indicator for multi-selection
        if (this.selection.size > 1 && this.selection.has(entry.date)) {
          const stackIndicator = document.createElement("div");
          stackIndicator.className = "event-stack-indicator";
          stackIndicator.textContent = this.selection.size.toString();
          body.appendChild(stackIndicator);

          // Add staggered positioning class to show stack effect
          chip.classList.add("stacked-chip");
        }
      } else {
        const empty = document.createElement("p");
        empty.className = "day-empty";
        empty.textContent = "No entry yet";
        body.appendChild(empty);
      }

      cell.appendChild(header);
      cell.appendChild(body);

      cell.addEventListener("click", (event) =>
        this.handleDayClick(event, entry, cell),
      );
      cell.addEventListener("dragover", (event) =>
        this.handleDragOver(event, cell),
      );
      cell.addEventListener("dragleave", () =>
        cell.classList.remove("drag-target"),
      );
      cell.addEventListener("drop", (event) => this.handleDrop(event, cell));

      return cell;
    }

    handleDayClick(event, entry, cell) {
      if (event.target.closest(".day-add")) {
        return;
      }
      const additive = event.metaKey || event.ctrlKey;
      if (event.shiftKey || additive) {
        this.updateSelection(entry.date, {
          shiftKey: event.shiftKey,
          additive,
        });
        return;
      }
      this.setSingleSelection(entry.date);
      this.openPopover(entry.date, cell);
    }

    handleEventClick(event, entry, cell) {
      const additive = event.metaKey || event.ctrlKey;
      if (event.shiftKey || additive) {
        event.stopPropagation();
        this.updateSelection(entry.date, {
          shiftKey: event.shiftKey,
          additive,
        });
        return;
      }
      event.stopPropagation();
      this.setSingleSelection(entry.date);
      this.openPopover(entry.date, cell);
    }

    updateSelection(date, options = {}) {
      const { shiftKey = false, additive = false } = options;
      if (shiftKey && this.lastSelectedDate) {
        const range = this.buildRange(this.lastSelectedDate, date);
        range.forEach((item) => this.selection.add(item));
        this.lastSelectedDate = date;
      } else if (additive) {
        if (this.selection.has(date)) {
          this.selection.delete(date);
        } else {
          this.selection.add(date);
        }
        this.lastSelectedDate = date;
      } else {
        this.setSingleSelection(date);
      }
      this.updateSelectionClasses();
    }

    setSingleSelection(date) {
      this.selection.clear();
      if (date) {
        this.selection.add(date);
        this.lastSelectedDate = date;
      } else {
        this.lastSelectedDate = null;
      }
      this.updateSelectionClasses();
    }

    buildRange(startDate, endDate) {
      if (!startDate || !endDate) {
        return [];
      }
      const start = parseISODate(startDate);
      const end = parseISODate(endDate);
      const step = start <= end ? 1 : -1;
      const range = [];
      let cursor = start;
      while (true) {
        range.push(formatISODate(cursor));
        if (cursor.getTime() === end.getTime()) {
          break;
        }
        cursor = addDays(cursor, step);
      }
      return range;
    }

    updateSelectionClasses() {
      if (!this.scrollEl) {
        return;
      }
      const cells = this.scrollEl.querySelectorAll(".calendar-day");
      cells.forEach((cell) => {
        const cellDate = cell.dataset.date;
        if (cellDate && this.selection.has(cellDate)) {
          cell.classList.add("is-selected");
        } else {
          cell.classList.remove("is-selected");
        }
      });

      // Update toolbar visibility for batch operations
      if (this.batchToolbarEl && this.selectionCountEl) {
        if (this.selection.size > 1) {
          this.batchToolbarEl.hidden = false;
          this.selectionCountEl.textContent = `${this.selection.size} selected`;
        } else {
          this.batchToolbarEl.hidden = true;
        }
      }

      // Force rebuild of current month to update stacking indicators
      if (this.currentYear && this.currentMonth) {
        // Find current month section and rebuild its cells to update stacking indicators
        const currentMonthKey = this.monthKey(this.currentYear, this.currentMonth);
        const currentMonthSection = this.visibleMonths.find(m => m.key === currentMonthKey);
        if (currentMonthSection) {
          const grid = currentMonthSection.el.querySelector('.calendar-grid');
          if (grid) {
            // Rebuild all cells for this month
            grid.innerHTML = '';
            const monthEntries = this.monthEntries.get(currentMonthKey) || [];
            monthEntries.forEach(dateKey => {
              const entry = this.entriesIndex.get(dateKey);
              if (entry) {
                grid.appendChild(this.buildDayCell(entry));
              }
            });
          }
        }
      }
    }

    handleDragStart(event, entry) {
      if (!entry || entry.is_missing) {
        event.preventDefault();
        return;
      }
      if (!this.selection.has(entry.date)) {
        this.setSingleSelection(entry.date);
      }
      this.dragOriginDate = entry.date;
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData(
          "application/json",
          JSON.stringify({ sourceDates: Array.from(this.selection) }),
        );
      }
    }

    handleDragEnd() {
      this.dragOriginDate = null;
      this.clearAutoScroll();
      if (!this.scrollEl) {
        return;
      }
      const cells = this.scrollEl.querySelectorAll(".calendar-day");
      cells.forEach((cell) => cell.classList.remove("drag-target"));
    }

    handleDragOver(event, cell) {
      if (!this.selection.size) {
        return;
      }
      event.preventDefault();
      cell.classList.add("drag-target");
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "move";
      }

      // Auto-scroll logic
      this.handleAutoScroll(event);
    }

    handleDrop(event, cell) {
      if (!this.selection.size) {
        return;
      }
      event.preventDefault();
      cell.classList.remove("drag-target");
      const targetDate = cell.dataset.date;
      if (!targetDate) {
        return;
      }
      this.moveSelection(targetDate, this.dragOriginDate);
    }

    async moveSelection(targetDate, anchorDate = null) {
      const sources = Array.from(this.selection);
      if (!sources.length || !targetDate) {
        return;
      }
      try {
        if (sources.length === 1) {
          const source = sources[0];
          if (source === targetDate) {
            return;
          }
          await this.jsonFetch(`/api/entry/${source}/move`, {
            new_date: targetDate,
          });
          this.showFlash("success", `Moved event to ${targetDate}.`);
        } else {
          const earliest = [...sources].sort()[0];
          const origin = anchorDate || earliest;
          const earliestDate = parseISODate(earliest);
          const originDate = parseISODate(origin);
          const targetDateObj = parseISODate(targetDate);
          const deltaDays = differenceInDays(originDate, targetDateObj);
          const targetForEarliest = formatISODate(
            addDays(earliestDate, deltaDays),
          );
          await this.jsonFetch("/api/entries/move", {
            source_dates: sources,
            target_date: targetForEarliest,
          });
          this.showFlash("success", `Moved ${sources.length} events.`);
        }
        await this.refreshFocusedMonth();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to move events");
      }
    }

    async submitPopover() {
      if (!this.popoverDateInput || !this.selectorInput) {
        return;
      }
      const date = this.popoverDateInput.value;
      const selector = this.selectorInput.value.trim();
      const status = this.statusInput.value;
      const notes = this.notesInput.value;
      const overrideRaw = this.overrideInput.value.trim();
      if (!selector) {
        this.showFlash("error", "Selector is required");
        this.selectorInput.focus();
        return;
      }
      const payload = {
        date,
        selector,
        status: status || null,
        notes,
        override: overrideRaw ? overrideRaw : null,
      };
      try {
        await this.jsonFetch("/api/entry", payload);
        this.closePopover();
        this.showFlash("success", "Entry saved.");
        await this.refreshFocusedMonth();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to save entry");
      }
    }

    async handleDelete() {
      const date = this.popoverDateInput?.value;
      if (!date) {
        return;
      }
      if (!confirm(`Are you sure you want to delete the entry for ${this.fullFormatter.format(parseISODate(date))}?`)) {
        return;
      }
      try {
        await this.jsonFetch(`/api/entry/${date}`, null, "DELETE");
        this.closePopover();
        this.showFlash("success", "Entry deleted.");
        await this.refreshFocusedMonth();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to delete entry");
      }
    }

    openPopover(date, anchor, resetOnly = false) {
      if (!this.popoverEl) {
        return;
      }
      
      // Hide all other overlays before showing this one
      this.hideAllOverlaysExcept('calendar-popover');
      
      const entry = this.entriesIndex.get(date);
      const isMissing = !entry || entry.is_missing || resetOnly;
      this.popoverDateInput.value = date;
      if (this.popoverDateLabel) {
        this.popoverDateLabel.textContent = this.fullFormatter.format(
          parseISODate(date),
        );
      }
      if (this.popoverSentMeta) {
        this.popoverSentMeta.textContent =
          entry && entry.sent_at ? `Sent at ${entry.sent_at}` : "";
      }
      this.selectorInput.value = isMissing ? "" : entry.selector || "";
      this.statusInput.value = isMissing ? "" : entry.status || "";
      this.notesInput.value = isMissing ? "" : entry.notes || "";
      this.overrideInput.value = isMissing ? "" : entry.override || "";
      this.popoverEl.hidden = false;
      this.activePopoverAnchor = anchor || null;
      this.positionPopover(anchor);
      setTimeout(() => {
        this.selectorInput.focus();
      }, 50);
    }

    positionPopover(anchor) {
      if (!anchor) {
        return;
      }
      const anchorRect = anchor.getBoundingClientRect();
      const popoverRect = this.popoverEl.getBoundingClientRect();
      let top = anchorRect.bottom + window.scrollY + 8;
      let left = anchorRect.left + window.scrollX;
      const maxLeft =
        window.scrollX + window.innerWidth - popoverRect.width - 16;
      const maxTop =
        window.scrollY + window.innerHeight - popoverRect.height - 16;
      left = Math.min(Math.max(16, left), Math.max(16, maxLeft));
      if (top > maxTop) {
        top = anchorRect.top + window.scrollY - popoverRect.height - 8;
      }
      top = Math.max(16, top);
      this.popoverEl.style.top = `${top}px`;
      this.popoverEl.style.left = `${left}px`;
    }

    closePopover() {
      if (!this.popoverEl) {
        return;
      }
      this.popoverEl.hidden = true;
      this.activePopoverAnchor = null;
    }

    showDateAdjustOverlay() {
      if (!this.dateAdjustOverlay) {
        return;
      }
      // Hide all other overlays before showing this one
      this.hideAllOverlaysExcept('date-adjust-overlay');
      
      const earliest = [...this.selection].sort()[0];
      this.dateAdjustInput.value = earliest || "";
      this.dateAdjustOverlay.hidden = false;
      this.dateAdjustInput.focus();
    }

    hideDateAdjustOverlay() {
      if (this.dateAdjustOverlay) {
        this.dateAdjustOverlay.hidden = true;
      }
    }

    showBatchEditOverlay() {
      if (!this.batchEditOverlay || !this.selection.size) {
        return;
      }

      // Hide all other overlays before showing this one
      this.hideAllOverlaysExcept('batch-edit-overlay');

      // Clear form
      if (this.batchSelectorInput) {
        this.batchSelectorInput.value = "";

        // Apply UI config from backend
        if (this.batchUIConfig) {
          this.batchSelectorInput.placeholder = this.batchUIConfig.placeholder;
          this.updateBatchHelpText(this.batchUIConfig.help_text);

          if (this.batchUIConfig.supports_range && this.batchUIConfig.range_example) {
            this.updateBatchRangeHint(this.batchUIConfig.range_example);
          } else {
            this.updateBatchRangeHint("");
          }
        }
      }

      if (this.batchStatusInput) this.batchStatusInput.value = "";
      if (this.batchNotesInput) this.batchNotesInput.value = "";
      if (this.batchOverrideInput) this.batchOverrideInput.value = "";
      this.batchEditOverlay.hidden = false;

      // Focus on selector input
      setTimeout(() => {
        this.batchSelectorInput?.focus();
      }, 100);
    }

    updateBatchHelpText(text) {
      const helpEl = document.getElementById("batch-selector-help");
      if (helpEl) {
        helpEl.textContent = text;
      }
    }

    updateBatchRangeHint(example) {
      const hintEl = document.getElementById("batch-range-hint");
      if (hintEl) {
        if (example) {
          hintEl.textContent = `💡 Range syntax: ${example}`;
          hintEl.hidden = false;
        } else {
          hintEl.hidden = true;
        }
      }
    }

    hideBatchEditOverlay() {
      if (this.batchEditOverlay) {
        this.batchEditOverlay.hidden = true;
      }
    }

    async submitBatchEdit() {
      if (!this.selection.size) {
        return;
      }

      const selectorInput = this.batchSelectorInput?.value.trim() || "";

      // If no selector input, proceed with other fields only
      let selectors = [];
      if (selectorInput) {
        // Parse selectors via backend API
        try {
          const parseResponse = await this.jsonFetch(
            "/api/batch-edit/parse-selectors",
            { input_text: selectorInput }
          );
          selectors = parseResponse.selectors;
        } catch (error) {
          this.showFlash("error", error.message || "Invalid selector format");
          this.batchSelectorInput?.focus();
          return;
        }

        // Validate selector count matches date count (unless single selector)
        if (selectors.length > 1 && selectors.length !== this.selection.size) {
          this.showFlash(
            "error",
            `Selector count (${selectors.length}) must match selected dates (${this.selection.size}), or use 1 selector for all.`
          );
          this.batchSelectorInput?.focus();
          return;
        }
      }

      const status = this.batchStatusInput?.value || null;
      const notes = this.batchNotesInput?.value.trim() || null;
      const override = this.batchOverrideInput?.value.trim() || null;

      // Sort selected dates chronologically
      const sortedDates = Array.from(this.selection).sort();

      // Build entries array
      const entries = sortedDates.map((date, index) => ({
        date,
        selector: selectors.length > 0 ? selectors[index % selectors.length] : undefined,
        status: status || undefined,
        notes: notes || undefined,
        override: override || undefined,
      }));

      try {
        await this.jsonFetch("/api/entries/batch", { entries });
        this.hideBatchEditOverlay();
        this.showFlash("success", `Updated ${this.selection.size} entries.`);
        await this.refreshFocusedMonth();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to update entries");
      }
    }

    async handleBatchDelete() {
      if (!this.selection.size) {
        return;
      }
      const dates = Array.from(this.selection).sort();
      const count = dates.length;

      if (!confirm(`Are you sure you want to delete ${count} selected ${count === 1 ? 'entry' : 'entries'}?`)) {
        return;
      }

      try {
        const result = await this.jsonFetch("/api/entries/batch-delete", dates);
        this.hideBatchEditOverlay();
        this.selection.clear();
        this.updateSelectionClasses();
        this.showFlash("success", `Deleted ${result.count} ${result.count === 1 ? 'entry' : 'entries'}.`);
        await this.refreshFocusedMonth();
      } catch (error) {
        this.showFlash("error", error.message || "Unable to delete entries");
      }
    }

    updateMonthYearLabel() {
      if (!this.monthYearEl || !this.currentYear || !this.currentMonth) {
        return;
      }
      const date = new Date(this.currentYear, this.currentMonth - 1, 1);
      this.monthYearEl.textContent = this.monthFormatter.format(date);
    }

    handleAutoScroll(event) {
      if (!this.scrollEl) {
        return;
      }

      const rect = this.scrollEl.getBoundingClientRect();
      const mouseY = event.clientY;
      const threshold = 50; // pixels from edge to trigger scroll

      // Clear existing timer
      this.clearAutoScroll();

      if (mouseY - rect.top < threshold) {
        // Scroll up (previous month)
        this.autoScrollTimer = setTimeout(() => {
          this.shiftMonth(-1);
        }, 300); // Delay to prevent too rapid scrolling
      } else if (rect.bottom - mouseY < threshold) {
        // Scroll down (next month)
        this.autoScrollTimer = setTimeout(() => {
          this.shiftMonth(1);
        }, 300);
      }
    }

    clearAutoScroll() {
      if (this.autoScrollTimer) {
        clearTimeout(this.autoScrollTimer);
        this.autoScrollTimer = null;
      }
    }

    showSessionExpiryFlash() {
      if (!this.flashContainer) {
        return;
      }

      // Remove any existing session expiry flash
      const existing = this.flashContainer.querySelector('.session-expiry-flash');
      if (existing) {
        existing.remove();
      }

      const flash = document.createElement("div");
      flash.className = "flash info session-expiry-flash";

      const messageSpan = document.createElement("span");
      messageSpan.textContent = "Welcome back! Your session expired. Redirecting in ";

      const countdownSpan = document.createElement("span");
      countdownSpan.className = "countdown";
      countdownSpan.textContent = "5 seconds";

      const button = document.createElement("button");
      button.className = "session-expiry-btn";
      button.textContent = "Login Now";
      button.addEventListener("click", () => {
        const currentUrl = encodeURIComponent(window.location.href);
        window.location.href = `/login-form?next=${currentUrl}`;
      });

      flash.appendChild(messageSpan);
      flash.appendChild(countdownSpan);
      flash.appendChild(document.createTextNode(" "));
      flash.appendChild(button);

      this.flashContainer.appendChild(flash);

      // Start countdown
      let countdown = 5;
      const countdownInterval = setInterval(() => {
        countdown--;
        countdownSpan.textContent = `${countdown} second${countdown <= 1 ? 's' : ''}`;

        if (countdown <= 0) {
          clearInterval(countdownInterval);
          const currentUrl = encodeURIComponent(window.location.href);
          window.location.href = `/login-form?next=${currentUrl}`;
        }
      }, 1000);

      // Clear countdown if flash is removed
      const clearCountdown = () => {
        clearInterval(countdownInterval);
        flash.removeEventListener('remove', clearCountdown);
      };
      flash.addEventListener('remove', clearCountdown);
    }

    showFlash(type, text) {
      if (!text || !this.flashContainer) {
        return;
      }
      const flash = document.createElement("div");
      flash.className = `flash ${type}`;
      flash.textContent = text;
      this.flashContainer.appendChild(flash);
      setTimeout(() => {
        flash.remove();
      }, 6000);
    }

    async jsonFetch(url, payload, method = "POST") {
      const response = await fetch(`${window.location.origin}${url}`, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (!response.ok) {
        throw new Error(await this.extractError(response));
      }
      return response.json();
    }

    async extractError(response) {
      if (response.status === 401) {
        // Handle session expiry with interactive countdown
        this.showSessionExpiryFlash();
        return "Session expired - redirecting to login...";
      }

      try {
        const data = await response.json();
        if (data.detail) {
          if (typeof data.detail === "string") {
            return data.detail;
          }
          if (Array.isArray(data.detail) && data.detail.length) {
            return data.detail[0].msg || "Request failed";
          }
        }
        return data.error || response.statusText || "Request failed";
      } catch (err) {
        return response.statusText || "Request failed";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const app = new CalendarApp(window.CalendarConfig || {});
    app.init();
    
    // Expose overlay management functions globally
    window.hideAllOverlaysExcept = (exceptId) => app.hideAllOverlaysExcept(exceptId);
    window.closeAllOverlays = () => app.closeAllOverlays();
  });
})();
