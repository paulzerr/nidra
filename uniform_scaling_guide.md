# Uniform UI Scaling - Implementation Guide

## Goal
Create a UI that scales uniformly (like zooming an image) when the browser window resizes, with easy adjustment via one or two control values. All elements maintain their proportions and nothing disappears off-screen.

## The Problem with Current Implementation

Your current code has **two critical bugs**:

1. **Line 18: Wrong DPI math**
   ```javascript
   const effective_scale = scale / dpi;  // ❌ DIVIDING by DPI
   ```
   Should be:
   ```javascript
   const effective_scale = scale;  // ✅ DON'T adjust for DPI at all
   ```
   The browser already handles DPI scaling. When you divide by devicePixelRatio, you're making elements *smaller* on high-DPI displays (MacBook Retina, high-res Windows, etc.).

2. **BASE_FONT_SCALE = 2.4 is way too large**
   This makes text 2.4x bigger than your base scale unit. Combined with viewport scaling, this creates massive elements.

## The Correct Implementation

### JavaScript: Simple, Robust Scaling Function

Replace your entire `scaleUi()` function with this:

```javascript
function initializeApp() {
    // ============================================
    // MASTER SCALING CONTROLS
    // Adjust these two values to resize entire UI
    // ============================================
    const MASTER_SCALE = 1.0;      // Overall size multiplier (1.0 = default)
    const DESIGN_WIDTH = 1920;     // Reference width for your design
    
    function scaleUi() {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        // Calculate scale based on how much smaller/larger than design width
        const baseScale = viewportWidth / DESIGN_WIDTH;
        
        // Apply master scale multiplier
        const finalScale = baseScale * MASTER_SCALE;
        
        // Set CSS variable that everything uses
        document.documentElement.style.setProperty('--scale', finalScale);
    }

    // Initial scale
    scaleUi();
    
    // Re-scale on window resize
    window.addEventListener('resize', scaleUi);
    
    // ... rest of your code
}
```

### CSS: Everything References One Scale Variable

Replace your CSS `:root` section:

```css
:root {
    /* Computed by JavaScript */
    --scale: 1;
    
    /* Base units - adjust these to resize entire UI */
    --base-unit: 16px;
    --base-font: 14px;
    
    /* All spacing derives from base units */
    --unit: calc(var(--base-unit) * var(--scale));
    --font-size: calc(var(--base-font) * var(--scale));
    
    /* Visual properties */
    --border-radius: calc(8px * var(--scale));
    --text-color: #333;
    --primary-color: #1a6887;
    --light-gray: #f0f2f5;
    --border-color: #d9d9d9;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--light-gray);
    height: 100vh;
    overflow: hidden;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: var(--font-size);
    line-height: 1.5;
}
```

### CSS: Update All Sizing to Use --unit

Replace your current sizing with consistent unit-based values:

```css
.container {
    display: flex;
    width: 95vw;
    height: 95vh;
    background-color: #ffffff;
    box-shadow: 0 calc(4px * var(--scale)) calc(12px * var(--scale)) rgba(0, 0, 0, 0.1);
    overflow: hidden;
    border: calc(1px * var(--scale)) solid var(--border-color);
    border-radius: var(--border-radius);
}

.panel {
    display: flex;
    flex-direction: column;
    padding: calc(var(--unit) * 1.5);
    overflow-y: auto;
}

.left-panel {
    flex: 1 1 50%;
    border-right: calc(1px * var(--scale)) solid var(--border-color);
    background-color: #fafafa;
    padding-right: calc(var(--unit) * 2);
}

.right-panel {
    flex: 1 1 50%;
    background-color: #2b2b2b;
    color: #f0f0f0;
    padding: calc(var(--unit) * 1.5);
    padding-left: calc(var(--unit) * 2);
}

.control-group {
    margin-bottom: calc(var(--unit) * 1.2);
}

.control-group h2 {
    font-size: calc(var(--font-size) * 1.2);
    font-weight: 600;
    margin-bottom: var(--unit);
    color: #1a1a1a;
}

hr {
    border: none;
    border-top: calc(1px * var(--scale)) solid #e0e0e0;
    margin: calc(var(--unit) * 1.5) 0;
}

label {
    font-size: var(--font-size);
    font-weight: 500;
    color: var(--text-color);
}

.file-input-group {
    display: flex;
    align-items: center;
    gap: calc(var(--unit) * 0.75);
}

input[type="text"], select {
    width: 100%;
    padding: calc(var(--unit) * 0.5) calc(var(--unit) * 0.75);
    border: calc(1px * var(--scale)) solid #ccc;
    border-radius: var(--border-radius);
    font-size: var(--font-size);
    background-color: #fff;
    height: calc(var(--unit) * 2.5);
}

.browse-btn, .help-btn {
    flex-shrink: 0;
    padding: 0 calc(var(--unit) * 1.25);
    border: calc(1px * var(--scale)) solid #ccc;
    border-radius: var(--border-radius);
    cursor: pointer;
    font-size: var(--font-size);
    font-weight: 500;
    transition: background-color 0.2s ease;
    background-color: #f5f5f5;
    color: var(--text-color);
    height: calc(var(--unit) * 2.5);
}

.browse-btn:hover, .help-btn:hover {
    background-color: #e9e9e9;
}

.radio-group {
    margin-top: calc(var(--unit) * 1.2);
    display: flex;
    flex-direction: column;
    gap: calc(var(--unit) * 0.5);
}

.radio-group label {
    display: flex;
    align-items: center;
    cursor: pointer;
}

input[type="radio"], input[type="checkbox"] {
    margin-right: calc(var(--unit) * 0.6);
    width: calc(var(--font-size) * 1.2);
    height: calc(var(--font-size) * 1.2);
    accent-color: var(--primary-color);
}

.flex-label {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: calc(var(--unit) * 1.5);
    align-items: center;
}

.horizontal-group {
    display: flex;
    flex-wrap: wrap;
    gap: calc(var(--unit) * 1.5);
    align-items: flex-end;
}

.sub-group {
    flex: 1;
    min-width: calc(var(--unit) * 12);
}

.sub-group label {
    display: block;
    margin-bottom: calc(var(--unit) * 0.6);
    font-size: calc(var(--font-size) * 1.2);
    font-weight: 600;
    color: #1a1a1a;
}

.options-group {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: calc(var(--unit) * 1.5);
    margin-bottom: calc(var(--unit) * 1.2);
}

.checkbox-group {
    display: flex;
    flex-direction: column;
    gap: calc(var(--unit) * 0.6);
}

.help-btn {
    flex-shrink: 0;
    width: 100%; 
}

.help-button-stack {
    display: flex;
    flex-direction: column;
    gap: calc(var(--unit) * 0.6);
    flex-shrink: 0; 
    width: 35%;
}

.run-btn {
    margin-top: auto;
    margin-bottom: calc(var(--unit) * 1.2);
    width: 100%;
    height: calc(var(--unit) * 3.5);
    padding: 0 calc(var(--unit) * 1.2);
    font-size: calc(var(--font-size) * 1.3);
    font-weight: 600;
    border: none;
    border-radius: var(--border-radius);
    background-color: var(--primary-color);
    color: white;
    cursor: pointer;
    transition: background-color 0.2s ease;
}

.run-btn:hover {
    background-color: #0979a1;
}

.run-btn:disabled {
    background-color: #1388b3;
    cursor: not-allowed;
}

.console-output {
    flex-grow: 1;
    background-color: #2b2b2b;
    color: #dcdcdc;
    border-radius: calc(6px * var(--scale));
    overflow-y: auto;
    font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
    font-size: calc(var(--font-size) * 0.9);
    height: 100%;
}

.console-output pre {
    padding: var(--unit);
    white-space: pre-wrap;
    word-wrap: break-word;
}

#select-channels-btn {
    margin-left: calc(var(--unit) * 0.6);
    height: auto;
    padding: calc(var(--unit) * 0.5) var(--unit);
    font-size: calc(var(--font-size) * 0.9);
    visibility: hidden;
}

#select-channels-btn.visible {
    visibility: visible;
}

.modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 1000;
    display: flex;
    justify-content: center;
    align-items: center;
}

.modal-content {
    background-color: #fff;
    padding: calc(var(--unit) * 2);
    border-radius: var(--border-radius);
    box-shadow: 0 calc(8px * var(--scale)) calc(24px * var(--scale)) rgba(0, 0, 0, 0.2);
    width: 90%;
    max-width: calc(var(--unit) * 35);
    max-height: 80vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    color: var(--text-color);
}

.modal-content h2 {
    font-size: calc(var(--font-size) * 1.2);
    margin-bottom: calc(var(--unit) * 1.2);
    color: #1a1a1a;
}

.modal-content form {
    display: flex;
    flex-direction: column;
    gap: calc(var(--unit) * 0.6);
    margin-bottom: calc(var(--unit) * 1.5);
}

.modal-content label {
    display: flex;
    align-items: center;
    cursor: pointer;
}

.modal-content .run-btn {
    margin-top: auto;
    width: 100%;
}
```

## How to Adjust the UI Size

You now have **two master controls** at the top of your JavaScript:

### 1. `MASTER_SCALE` - Overall Size Multiplier
```javascript
const MASTER_SCALE = 1.0;   // Default size
const MASTER_SCALE = 0.8;   // 20% smaller
const MASTER_SCALE = 1.2;   // 20% larger
```
This uniformly scales everything - fonts, spacing, buttons, everything.

### 2. `DESIGN_WIDTH` - Reference Resolution
```javascript
const DESIGN_WIDTH = 1920;  // Designed for 1920px width
const DESIGN_WIDTH = 1600;  // Designed for 1600px width
```
This determines what screen width shows the UI at "native" size. On a 1920px window with DESIGN_WIDTH=1920, scale=1.0. On a 1600px window, scale=0.83.

### Fine-Tuning Individual Elements

If you need to adjust just fonts or just spacing:

```css
:root {
    --base-unit: 16px;   /* Increase to make spacing larger */
    --base-font: 14px;   /* Increase to make text larger */
}
```

## Why This Works Universally

1. **No DPI Math**: The browser handles devicePixelRatio automatically. CSS pixels are already device-independent.

2. **Single Source of Truth**: Everything scales from `--scale` variable. Change one number, everything scales proportionally.

3. **Viewport-Based**: Uses actual window dimensions, not aspect ratios or complex formulas.

4. **Predictable**: Linear relationship between window size and UI size. 50% smaller window = 50% smaller UI.

5. **No Browser Differences**: Pure CSS calc() and viewport units work identically across all browsers.

## Testing & Calibration Process

1. **Set DESIGN_WIDTH to your current monitor's width** (e.g., 1920)
2. **Set MASTER_SCALE = 1.0**
3. **Resize browser window** - everything should scale proportionally
4. **If too large at default size**: Decrease MASTER_SCALE to 0.9 or 0.8
5. **If too small at default size**: Increase MASTER_SCALE to 1.1 or 1.2
6. **Test on different displays**: The ratio should remain consistent

## Expected Results

- ✅ UI scales uniformly like zooming an image
- ✅ Same proportions on all displays, DPI settings, and browsers
- ✅ Change 1-2 values to adjust entire UI
- ✅ No elements disappear off-screen
- ✅ Works on Windows 100%, 125%, 150% scaling
- ✅ Works on macOS Retina displays
- ✅ Smooth, predictable resizing behavior

## Migration Steps

1. Replace `scaleUi()` function with the new version
2. Update CSS `:root` variables
3. Find/replace all `var(--ui-scale)` with `var(--unit)` in CSS
4. Find/replace all `var(--font-scale)` with `var(--font-size)` in CSS
5. Test at multiple window sizes
6. Adjust MASTER_SCALE until it looks right
7. Test on different displays/browsers

The key insight: **Don't fight DPI scaling, ignore it.** The browser already knows how to display CSS pixels correctly on every device.