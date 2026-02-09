(function() {
  "use strict";

  // Caffeine mode UI functionality
  const caffeineIndicator = document.getElementById('caffeine-indicator');
  const caffeineOverlay = document.getElementById('caffeine-overlay');
  const caffeineCloseBtn = document.querySelector('.caffeine-close');
  const caffeineRefreshBtn = document.getElementById('caffeine-refresh-btn');
  const caffeineModeStatus = document.getElementById('caffeine-mode-status');
  const caffeineStatus = document.getElementById('caffeine-status');

  // Hide caffeine overlay
  function hideCaffeineOverlay() {
    if (caffeineOverlay) {
      caffeineOverlay.hidden = true;
    }
  }

  // Show caffeine overlay
  function showCaffeineOverlay() {
    if (caffeineOverlay) {
      // Hide all other overlays first
      if (window.hideAllOverlaysExcept) {
        window.hideAllOverlaysExcept('caffeine-overlay');
      }
      caffeineOverlay.hidden = false;
      // Position overlay
      const indicatorRect = caffeineIndicator.getBoundingClientRect();
      const center = caffeineOverlay.querySelector('.caffeine-center');
      
      // Show off-screen to measure width
      caffeineOverlay.style.top = '-1000px';
      caffeineOverlay.hidden = false;
      
      const panelWidth = center.offsetWidth;
      
      // Position under indicator
      caffeineOverlay.style.top = (indicatorRect.bottom + 8) + 'px';
      caffeineOverlay.style.left = (indicatorRect.left + indicatorRect.width / 2 - panelWidth / 2) + 'px';
    }
  }

  // Toggle caffeine overlay
  function toggleCaffeineOverlay() {
    if (caffeineOverlay && caffeineIndicator) {
      if (caffeineOverlay.hidden) {
        showCaffeineOverlay();
      } else {
        hideCaffeineOverlay();
      }
    }
  }

  // Close overlay when clicking outside
  document.addEventListener('click', function(e) {
    if (!caffeineOverlay || caffeineOverlay.hidden) {
      return;
    }
    
    const center = caffeineOverlay.querySelector('.caffeine-center');
    const isClickInsideOverlay = center.contains(e.target) || caffeineIndicator.contains(e.target);
    
    if (!isClickInsideOverlay) {
      hideCaffeineOverlay();
    }
  });

  // Check caffeine mode status
  async function checkCaffeineModeStatus() {
    try {
      const response = await fetch('/api/caffeine-status', {
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error('Failed to check caffeine mode status');
      }
      
      const data = await response.json();
      
      // Update UI status
      if (caffeineModeStatus) {
        if (data.enabled) {
          caffeineModeStatus.innerHTML = `
            <span class="caffeine-status-active">
              ✓ Caffeine mode is active
            </span>
          `;
        } else {
          caffeineModeStatus.innerHTML = `
            <span class="caffeine-status-inactive">
              ⚠️ Caffeine mode is inactive
            </span>
          `;
        }
      }
      
      // Update indicator status
      if (caffeineStatus) {
        if (data.enabled) {
          caffeineStatus.textContent = '●'; // Active indicator
          caffeineStatus.style.color = '#10b981'; // Green
        } else {
          caffeineStatus.textContent = '○'; // Inactive indicator
          caffeineStatus.style.color = '#6b7280'; // Gray
        }
      }
      
      // Update indicator class
      if (caffeineIndicator) {
        if (data.enabled) {
          caffeineIndicator.classList.add('caffeine-active');
          caffeineIndicator.classList.remove('caffeine-inactive');
        } else {
          caffeineIndicator.classList.add('caffeine-inactive');
          caffeineIndicator.classList.remove('caffeine-active');
        }
      }
      
      return data;
    } catch (error) {
      console.error('Error checking caffeine mode status:', error);
      if (caffeineModeStatus) {
        caffeineModeStatus.innerHTML = `
          <span class="caffeine-status-error">
            ❌ Unable to check caffeine mode status
          </span>
        `;
      }
      return { enabled: false };
    }
  }

  // Event listeners
  if (caffeineIndicator) {
    caffeineIndicator.addEventListener('click', function(e) {
      e.preventDefault();
      toggleCaffeineOverlay();
    });
  }

  if (caffeineCloseBtn) {
    caffeineCloseBtn.addEventListener('click', function(e) {
      e.preventDefault();
      hideCaffeineOverlay();
    });
  }

  if (caffeineRefreshBtn) {
    caffeineRefreshBtn.addEventListener('click', async function(e) {
      e.preventDefault();
      await checkCaffeineModeStatus();
    });
  }

  // Initialize caffeine mode status on page load
  document.addEventListener('DOMContentLoaded', async function() {
    await checkCaffeineModeStatus();
  });

  // Expose functions globally
  window.hideCaffeineOverlay = hideCaffeineOverlay;
  window.showCaffeineOverlay = showCaffeineOverlay;
  window.toggleCaffeineOverlay = toggleCaffeineOverlay;
  window.checkCaffeineModeStatus = checkCaffeineModeStatus;
})();