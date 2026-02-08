# Overlay Management System

This document describes the centralized overlay management system implemented for the Daily Manna Email dashboard.

## Overview

The overlay management system provides a unified way to handle all modal panels and overlays in the application. It ensures consistent behavior, proper keyboard navigation, and easy extensibility for future panels.

## Architecture

### Core Components

1. **Common CSS Class**: All overlays use the `overlay` class for consistent styling and behavior
2. **Centralized JavaScript Functions**: Core overlay management functions in `calendar.js`
3. **Individual Panel Functions**: Each panel maintains its specific show/hide logic
4. **Global Window Functions**: Exposed functions for cross-panel communication

### Overlay Classes

All overlays should use the `overlay` class:

```html
<div id="panel-id" class="overlay" hidden>
  <!-- Panel content -->
</div>
```

### Core Management Functions

#### `closeAllOverlays()`
Closes all overlays at once. Called when:
- User presses Escape key
- New overlay needs to be shown exclusively
- Application state requires clearing all panels

#### `isOverlayVisible(overlayId)`
Checks if a specific overlay is visible.

#### `hideAllOverlaysExcept(exceptId)`
Hides all overlays except the specified one. Useful for showing one panel while closing others.

#### `hideNotificationOverlay()` and `hideDispatchOverlay()`
Individual hide functions exposed globally for cross-panel communication.

## Implementation Details

### HTML Structure

Each overlay should follow this pattern:

```html
<div id="overlay-id" class="overlay" hidden role="dialog" aria-modal="true" aria-labelledby="overlay-title">
  <div class="overlay-content">
    <header>
      <h3 id="overlay-title">Panel Title</h3>
      <button class="overlay-close" aria-label="Close">×</button>
    </header>
    <!-- Panel content -->
  </div>
</div>
```

### CSS Classes

- `.overlay`: Base class for all overlays
- `.overlay[hidden]`: Hidden state (default)
- `.overlay.visible`: Visible state (optional, for animations)
- `.overlay-content`: Main content container
- `.overlay-close`: Close button styling

### JavaScript Integration

#### In calendar.js

```javascript
// Centralized functions
closeAllOverlays() {
  this.closePopover();
  this.hideDateAdjustOverlay();
  this.hideBatchEditOverlay();
  this.hideNotificationOverlay();
  this.hideDispatchOverlay();
}

// Individual functions
hideNotificationOverlay() {
  const overlay = document.getElementById('notification-overlay');
  if (overlay) {
    overlay.hidden = true;
  }
}
```

#### In individual panel files

```javascript
// Expose hide function globally
window.hidePanelName = hidePanelName;

function hidePanelName() {
  const overlay = document.getElementById('panel-id');
  if (overlay) {
    overlay.hidden = true;
  }
}
```

## Panel-Specific Implementation

### Calendar Popover
- **File**: `calendar.js`
- **ID**: `calendar-popover`
- **Features**: Dynamic positioning, form handling, drag-and-drop integration

### Date Adjust Overlay
- **File**: `calendar.js`
- **ID**: `date-adjust-overlay`
- **Features**: Date picker, form validation, batch operations

### Batch Edit Overlay
- **File**: `calendar.js`
- **ID**: `batch-edit-overlay`
- **Features**: Multi-field forms, backend integration, validation

### Notification Overlay
- **File**: `dashboard.html` (inline)
- **ID**: `notification-overlay`
- **Features**: Real-time updates, pagination, filtering

### Dispatch Overlay
- **File**: `dispatch_rules.js`
- **ID**: `dispatch-overlay`
- **Features**: Dynamic content loading, polling, form handling

## Keyboard Navigation

- **Escape**: Closes all overlays
- **Enter/Space**: Activates focused buttons
- **Tab**: Navigates within overlay content

## Event Handling

### Click Outside to Close
Each overlay handles clicks outside its bounds:

```javascript
document.addEventListener('click', (event) => {
  if (overlay.hidden) return;
  if (!overlay.contains(event.target) && !triggerButton.contains(event.target)) {
    closeOverlay();
  }
});
```

### Resize Handling
Overlays that need repositioning on window resize:

```javascript
window.addEventListener('resize', () => {
  if (!overlay.hidden) {
    positionOverlay();
  }
});
```

## Extending the System

### Adding a New Overlay

1. **Create HTML Structure**:
   ```html
   <div id="new-overlay" class="overlay" hidden>
     <!-- Content -->
   </div>
   ```

2. **Add CSS Styling**:
   ```css
   #new-overlay {
     /* Panel-specific styles */
   }
   ```

3. **Implement JavaScript Functions**:
   ```javascript
   function showNewOverlay() {
     hideAllOverlaysExcept('new-overlay');
     document.getElementById('new-overlay').hidden = false;
   }
   
   function hideNewOverlay() {
     document.getElementById('new-overlay').hidden = true;
   }
   
   // Expose globally
   window.hideNewOverlay = hideNewOverlay;
   ```

4. **Update Central Management**:
   ```javascript
   // In calendar.js
   closeAllOverlays() {
     // ... existing calls
     this.hideNewOverlay();
   }
   
   hideAllOverlaysExcept(exceptId) {
     const overlayIds = [
       // ... existing IDs
       'new-overlay'
     ];
     // ... existing logic
   }
   ```

5. **Add Event Listeners**:
   ```javascript
   // Click outside to close
   document.addEventListener('click', (event) => {
     // ... existing logic
   });
   
   // Keyboard support
   document.addEventListener('keydown', (event) => {
     if (event.key === 'Escape') {
       closeAllOverlays();
     }
   });
   ```

### Best Practices

1. **Consistent IDs**: Use kebab-case for overlay IDs
2. **Accessibility**: Include proper ARIA attributes
3. **Keyboard Support**: Ensure all interactive elements are keyboard accessible
4. **Focus Management**: Set focus appropriately when opening overlays
5. **State Management**: Clear form data when closing overlays
6. **Error Handling**: Gracefully handle missing elements or failed operations

### Performance Considerations

1. **Lazy Loading**: Load overlay content only when needed
2. **Event Delegation**: Use event delegation for dynamic content
3. **Memory Management**: Clean up event listeners when overlays are removed
4. **CSS Transitions**: Use CSS for animations rather than JavaScript

## Testing

A test file is provided at `test_overlay_management.html` to verify the overlay management system works correctly.

### Test Scenarios

1. **Individual Overlay Control**: Show/hide each overlay independently
2. **Bulk Operations**: Show all overlays, then close all
3. **Keyboard Navigation**: Test Escape key functionality
4. **Cross-Panel Communication**: Verify that showing one overlay closes others
5. **State Persistence**: Ensure overlay state is properly managed

### Running Tests

Open `test_overlay_management.html` in a browser and use the test controls to verify functionality.

## Troubleshooting

### Common Issues

1. **Overlays Not Closing**: Check that `hidden` attribute is being set correctly
2. **Keyboard Events Not Working**: Verify event listeners are attached to document
3. **Click Outside Not Working**: Ensure event delegation is properly implemented
4. **Focus Issues**: Check that focus is managed correctly when opening/closing overlays

### Debug Tips

1. **Console Logging**: Add console.log statements to show/hide functions
2. **DOM Inspection**: Use browser dev tools to inspect overlay states
3. **Event Monitoring**: Use dev tools to monitor event listeners
4. **CSS Debugging**: Temporarily remove `hidden` attribute to test styling

## Future Enhancements

### Potential Improvements

1. **Animation Support**: Add CSS transitions for smoother overlay transitions
2. **Stacking Context**: Implement proper z-index management for multiple overlays
3. **Mobile Optimization**: Add touch-friendly interactions and responsive design
4. **Accessibility**: Enhance ARIA support and screen reader compatibility
5. **State Persistence**: Save/restore overlay state across page reloads

### Extension Points

1. **Overlay Registry**: Create a central registry of all overlays
2. **Event System**: Implement a custom event system for overlay communication
3. **Configuration**: Add configuration options for overlay behavior
4. **Plugins**: Support for plugin-based overlay extensions