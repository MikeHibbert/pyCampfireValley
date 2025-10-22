// CampfireValley LiteGraph Nodes - Complete UI Replacement

// ===== TEXT MEASUREMENT AND DYNAMIC SIZING UTILITIES =====

// Text measurement utility to calculate required dimensions
class TextMeasurement {
    
    static getContext() {
        if (!this.canvas) {
            this.canvas = document.createElement('canvas');
            this.ctx = this.canvas.getContext('2d');
        }
        return this.ctx;
    }
    
    static measureText(text, font, maxWidth) {
        if (font === undefined) font = '12px Arial';
        if (maxWidth === undefined) maxWidth = null;
        const ctx = this.getContext();
        ctx.font = font;
        
        if (!text || text.length === 0) {
            return { width: 0, height: 16 };
        }
        
        const lines = maxWidth ? this.wrapText(text, maxWidth, ctx) : [text];
        const lineHeight = parseInt(font) * 1.2; // 1.2 is typical line height multiplier
        
        let maxLineWidth = 0;
        lines.forEach(line => {
            const metrics = ctx.measureText(line);
            maxLineWidth = Math.max(maxLineWidth, metrics.width);
        });
        
        return {
            width: Math.ceil(maxLineWidth),
            height: Math.ceil(lines.length * lineHeight),
            lines: lines
        };
    }
    
    static wrapText(text, maxWidth, ctx) {
        const words = text.split(' ');
        const lines = [];
        let currentLine = '';
        
        for (let word of words) {
            const testLine = currentLine + (currentLine ? ' ' : '') + word;
            const metrics = ctx.measureText(testLine);
            
            if (metrics.width > maxWidth && currentLine) {
                lines.push(currentLine);
                currentLine = word;
            } else {
                currentLine = testLine;
            }
        }
        
        if (currentLine) {
            lines.push(currentLine);
        }
        
        return lines;
    }
}

TextMeasurement.canvas = null;
TextMeasurement.ctx = null;

// Collision detection and layout utilities
class CollisionDetection {
    static checkBoundingBoxCollision(rect1, rect2) {
        return !(rect1.x + rect1.width < rect2.x || 
                rect2.x + rect2.width < rect1.x || 
                rect1.y + rect1.height < rect2.y || 
                rect2.y + rect2.height < rect1.y);
    }
    
    static findNonCollidingPosition(newNode, existingNodes, spacing = 20) {
        // Handle both node objects and plain rectangles
        const newRect = newNode.pos ? {
            x: newNode.pos[0],
            y: newNode.pos[1],
            width: newNode.size[0],
            height: newNode.size[1]
        } : {
            x: newNode.x,
            y: newNode.y,
            width: newNode.width,
            height: newNode.height
        };
        
        let attempts = 0;
        const maxAttempts = 100;
        const stepSize = 50;
        
        while (attempts < maxAttempts) {
            let hasCollision = false;
            
            for (let existingNode of existingNodes) {
                if (existingNode === newNode) continue;
                
                // Handle both node objects and plain rectangles
                const existingRect = existingNode.pos ? {
                    x: existingNode.pos[0] - spacing,
                    y: existingNode.pos[1] - spacing,
                    width: existingNode.size[0] + (spacing * 2),
                    height: existingNode.size[1] + (spacing * 2)
                } : {
                    x: existingNode.x - spacing,
                    y: existingNode.y - spacing,
                    width: existingNode.width + (spacing * 2),
                    height: existingNode.height + (spacing * 2)
                };
                
                if (this.checkBoundingBoxCollision(newRect, existingRect)) {
                    hasCollision = true;
                    break;
                }
            }
            
            if (!hasCollision) {
                return [newRect.x, newRect.y];
            }
            
            // Try different positions in a spiral pattern
            const angle = (attempts * 0.5) % (Math.PI * 2);
            const radius = Math.floor(attempts / 8) * stepSize + stepSize;
            
            const originalX = newNode.pos ? newNode.pos[0] : newNode.x;
            const originalY = newNode.pos ? newNode.pos[1] : newNode.y;
            
            newRect.x = originalX + Math.cos(angle) * radius;
            newRect.y = originalY + Math.sin(angle) * radius;
            
            attempts++;
        }
        
        // If no position found, place it far to the right
        const fallbackX = newNode.pos ? newNode.pos[0] : newNode.x;
        const fallbackY = newNode.pos ? newNode.pos[1] : newNode.y;
        return [fallbackX + (existingNodes.length * 300), fallbackY];
    }
}

// Dynamic sizing mixin for nodes
const DynamicSizingMixin = {
    calculateDynamicSize: function(content, minWidth = 160, minHeight = 100, padding = 20) {
        if (!content || typeof content !== 'string') {
            return [minWidth, minHeight];
        }
        
        const maxTextWidth = Math.max(200, minWidth - padding * 2);
        const measurement = TextMeasurement.measureText(content, '12px Arial', maxTextWidth);
        
        const requiredWidth = Math.max(minWidth, measurement.width + padding * 2);
        const requiredHeight = Math.max(minHeight, measurement.height + padding * 2 + 40); // Extra space for title and widgets
        
        return [Math.ceil(requiredWidth), Math.ceil(requiredHeight)];
    },
    
    updateSizeBasedOnContent: function(content) {
        const newSize = this.calculateDynamicSize(content);
        if (newSize[0] !== this.size[0] || newSize[1] !== this.size[1]) {
            this.size = newSize;
            this.setDirtyCanvas(true, true);
            return true;
        }
        return false;
    },
    
    drawWrappedText: function(ctx, text, x, y, maxWidth, lineHeight = 16) {
        if (!text) return y;
        
        const lines = TextMeasurement.wrapText(text, maxWidth, ctx);
        let currentY = y;
        
        lines.forEach(line => {
            ctx.fillText(line, x, currentY);
            currentY += lineHeight;
        });
        
        return currentY;
    },
    
    // Enhanced dynamic sizing methods
    calculateRequiredHeight: function(drawingFunction, padding = 20) {
        // Create a temporary canvas to measure the actual drawing height
        const tempCanvas = document.createElement('canvas');
        const tempCtx = tempCanvas.getContext('2d');
        tempCanvas.width = this.size[0];
        tempCanvas.height = 1000; // Large height for measurement
        
        // Set up the context with the same font settings
        tempCtx.font = '12px Arial';
        tempCtx.fillStyle = '#ffffff';
        
        // Track the maximum Y position reached during drawing
        let maxY = 0;
        const originalFillText = tempCtx.fillText;
        const originalFillRect = tempCtx.fillRect;
        const originalArc = tempCtx.arc;
        
        // Override drawing methods to track Y positions
        tempCtx.fillText = function(text, x, y) {
            maxY = Math.max(maxY, y + 12); // Add font height
            return originalFillText.call(this, text, x, y);
        };
        
        tempCtx.fillRect = function(x, y, width, height) {
            maxY = Math.max(maxY, y + height);
            return originalFillRect.call(this, x, y, width, height);
        };
        
        tempCtx.arc = function(x, y, radius, startAngle, endAngle) {
            maxY = Math.max(maxY, y + radius);
            return originalArc.call(this, x, y, radius, startAngle, endAngle);
        };
        
        // Execute the drawing function
        try {
            drawingFunction.call(this, tempCtx);
        } catch (e) {
            console.warn('Error measuring node height:', e);
            return this.size[1]; // Return current height on error
        }
        
        // Restore original methods
        tempCtx.fillText = originalFillText;
        tempCtx.fillRect = originalFillRect;
        tempCtx.arc = originalArc;
        
        return Math.max(this.size[1], maxY + padding);
    },
    
    autoSizeNode: function(drawingFunction, minWidth = null, padding = 20) {
        const currentWidth = minWidth || this.size[0];
        const requiredHeight = this.calculateRequiredHeight(drawingFunction, padding);
        
        const newSize = [currentWidth, Math.ceil(requiredHeight)];
        
        if (newSize[0] !== this.size[0] || newSize[1] !== this.size[1]) {
            this.size = newSize;
            this.setDirtyCanvas(true, true);
            return true;
        }
        return false;
    },
    
    // Helper method to add widget height to node
    addWidgetHeight: function(widgetHeight, padding = 10) {
        const newHeight = this.size[1] + widgetHeight + padding;
        if (newHeight !== this.size[1]) {
            this.size[1] = newHeight;
            this.setDirtyCanvas(true, true);
            return true;
        }
        return false;
    },
    
    // Widget overlap detection and resolution
    detectWidgetOverlaps: function() {
        if (!this.widgets || this.widgets.length < 2) {
            return [];
        }
        
        const overlaps = [];
        for (let i = 0; i < this.widgets.length; i++) {
            for (let j = i + 1; j < this.widgets.length; j++) {
                const widget1 = this.widgets[i];
                const widget2 = this.widgets[j];
                
                const overlap = this.calculateWidgetOverlap(widget1, widget2);
                if (overlap.hasOverlap) {
                    overlaps.push({
                        widget1: widget1,
                        widget2: widget2,
                        overlap: overlap
                    });
                }
            }
        }
        return overlaps;
    },
    
    calculateWidgetOverlap: function(widget1, widget2) {
        // Get widget bounds
        const bounds1 = this.getWidgetBounds(widget1);
        const bounds2 = this.getWidgetBounds(widget2);
        
        // Check for overlap
        const hasOverlap = !(bounds1.right <= bounds2.left || 
                           bounds2.right <= bounds1.left || 
                           bounds1.bottom <= bounds2.top || 
                           bounds2.bottom <= bounds1.top);
        
        if (!hasOverlap) {
            return { hasOverlap: false };
        }
        
        // Calculate overlap area and direction
        const overlapLeft = Math.max(bounds1.left, bounds2.left);
        const overlapRight = Math.min(bounds1.right, bounds2.right);
        const overlapTop = Math.max(bounds1.top, bounds2.top);
        const overlapBottom = Math.min(bounds1.bottom, bounds2.bottom);
        
        const overlapWidth = overlapRight - overlapLeft;
        const overlapHeight = overlapBottom - overlapTop;
        const overlapArea = overlapWidth * overlapHeight;
        
        // Calculate widget areas
        const area1 = (bounds1.right - bounds1.left) * (bounds1.bottom - bounds1.top);
        const area2 = (bounds2.right - bounds2.left) * (bounds2.bottom - bounds2.top);
        
        // Determine majority overlap direction
        const widget1OverlapRatio = overlapArea / area1;
        const widget2OverlapRatio = overlapArea / area2;
        
        return {
            hasOverlap: true,
            overlapWidth: overlapWidth,
            overlapHeight: overlapHeight,
            overlapArea: overlapArea,
            widget1OverlapRatio: widget1OverlapRatio,
            widget2OverlapRatio: widget2OverlapRatio,
            bounds1: bounds1,
            bounds2: bounds2
        };
    },
    
    getWidgetBounds: function(widget) {
        // Default widget dimensions if not specified
        const widgetHeight = widget.height || 20;
        const widgetWidth = widget.width || (this.size[0] - 20);
        
        return {
            left: widget.x || 10,
            top: widget.y || 10,
            right: (widget.x || 10) + widgetWidth,
            bottom: (widget.y || 10) + widgetHeight
        };
    },
    
    resolveWidgetOverlaps: function(spacing = 5) {
        const overlaps = this.detectWidgetOverlaps();
        let resolutionsApplied = 0;
        
        for (const overlapInfo of overlaps) {
            const { widget1, widget2, overlap } = overlapInfo;
            
            // Determine which widget to move based on majority overlap
            let widgetToMove, staticWidget;
            if (overlap.widget1OverlapRatio > overlap.widget2OverlapRatio) {
                widgetToMove = widget1;
                staticWidget = widget2;
            } else {
                widgetToMove = widget2;
                staticWidget = widget1;
            }
            
            // Calculate new position
            const newPosition = this.calculateNonOverlappingPosition(
                widgetToMove, staticWidget, spacing
            );
            
            if (newPosition) {
                widgetToMove.y = newPosition.y;
                resolutionsApplied++;
            }
        }
        
        // If we resolved overlaps, check for new overlaps and resize node if needed
        if (resolutionsApplied > 0) {
            this.adjustNodeSizeForWidgets();
            this.setDirtyCanvas(true, true);
        }
        
        return resolutionsApplied;
    },
    
    calculateNonOverlappingPosition: function(widgetToMove, staticWidget, spacing = 5) {
        const movingBounds = this.getWidgetBounds(widgetToMove);
        const staticBounds = this.getWidgetBounds(staticWidget);
        
        // Try moving up first
        const moveUpY = staticBounds.top - (movingBounds.bottom - movingBounds.top) - spacing;
        if (moveUpY >= 10) { // Ensure minimum top margin
            return { y: moveUpY };
        }
        
        // If can't move up, move down
        const moveDownY = staticBounds.bottom + spacing;
        return { y: moveDownY };
    },
    
    adjustNodeSizeForWidgets: function() {
        if (!this.widgets || this.widgets.length === 0) {
            return;
        }
        
        // Find the bottom-most widget
        let maxBottom = 0;
        for (const widget of this.widgets) {
            const bounds = this.getWidgetBounds(widget);
            maxBottom = Math.max(maxBottom, bounds.bottom);
        }
        
        // Add padding and ensure minimum height
        const requiredHeight = Math.max(maxBottom + 20, 100);
        if (requiredHeight > this.size[1]) {
            this.size[1] = requiredHeight;
            this.setDirtyCanvas(true, true);
        }
    },
    
    // Enhanced autoSizeNode that includes overlap resolution
    autoSizeNodeWithOverlapResolution: function(drawingFunction, minWidth = null, padding = 20) {
        // First, auto-size based on content
        const sizeChanged = this.autoSizeNode(drawingFunction, minWidth, padding);
        
        // Then resolve any widget overlaps
        const overlapsResolved = this.resolveWidgetOverlaps();
        
        return sizeChanged || overlapsResolved > 0;
    },
    
    // Override addWidget to automatically resolve overlaps when widgets are added
    addWidget: function(type, name, value, callback, options) {
        // Call the original addWidget method
        const widget = LGraphNode.prototype.addWidget.call(this, type, name, value, callback, options);
        
        // Automatically resolve overlaps after adding widget
        setTimeout(() => {
            this.resolveWidgetOverlaps();
        }, 50);
        
        return widget;
    },
    
    // Method to manually trigger overlap resolution (useful for external calls)
    triggerOverlapResolution: function() {
        return this.resolveWidgetOverlaps();
    }
};

// ===== END UTILITIES =====

// Task Input Node - replaces task textarea and controls
function TaskInputNode() {
    this.addOutput("task_text", "string");
    this.addOutput("start_trigger", "trigger");
    this.addOutput("stop_trigger", "trigger");
    this.addProperty("task_description", "Enter a task for the campfires to process...");
    this.addProperty("status", "ready");
    
    // Calculate initial size based on content
    const initialSize = this.calculateDynamicSize(this.properties.task_description, 350, 220);
    this.size = initialSize;
    this.widgets_up = true;
    
    // Add large textarea widget for task input
    this.taskWidget = this.addWidget("text", "Task Description", this.properties.task_description, (v) => {
        this.properties.task_description = v;
        this.setOutputData(0, v);
        // Update size when content changes
        this.updateSizeBasedOnContent(v);
    });
    
    // Make the text widget larger and multiline
    if (this.taskWidget) {
        this.taskWidget.options = this.taskWidget.options || {};
        this.taskWidget.options.multiline = true;
        this.taskWidget.options.max_length = 1000;
        this.taskWidget.y = 60;
        this.taskWidget.height = 80;
    }
    
    this.addWidget("button", "🚀 Start Task", null, () => {
        this.properties.status = "running";
        this.triggerSlot(1);
        if (window.CampfireValley && window.CampfireValley.startTask) {
            window.CampfireValley.startTask(this.properties.task_description);
        }
    });
    
    this.addWidget("button", "⏹️ Stop Task", null, () => {
        this.properties.status = "ready";
        this.triggerSlot(2);
        if (window.CampfireValley && window.CampfireValley.stopTask) {
            window.CampfireValley.stopTask();
        }
    });
}

TaskInputNode.title = "Task Input";
TaskInputNode.desc = "Interactive task input and control";

TaskInputNode.prototype.onMouseDown = function(e, localpos, graphcanvas) {
    // Check if click is in the text area
    const textAreaX = 10;
    const textAreaY = 60;
    const textAreaWidth = this.size[0] - 20;
    const textAreaHeight = 80;
    
    if (localpos[0] >= textAreaX && localpos[0] <= textAreaX + textAreaWidth &&
        localpos[1] >= textAreaY && localpos[1] <= textAreaY + textAreaHeight) {
        
        // Create a temporary textarea for editing
        this.createTextEditor(graphcanvas, localpos);
        return true;
    }
    return false;
};

TaskInputNode.prototype.onMouseMove = function(e, localpos, graphcanvas) {
    // Change cursor to text cursor when hovering over text area
    const textAreaX = 10;
    const textAreaY = 60;
    const textAreaWidth = this.size[0] - 20;
    const textAreaHeight = 80;
    
    if (localpos[0] >= textAreaX && localpos[0] <= textAreaX + textAreaWidth &&
        localpos[1] >= textAreaY && localpos[1] <= textAreaY + textAreaHeight) {
        
        if (graphcanvas.canvas) {
            graphcanvas.canvas.style.cursor = 'text';
        }
        return true;
    } else {
        if (graphcanvas.canvas) {
            graphcanvas.canvas.style.cursor = 'default';
        }
    }
    return false;
};

TaskInputNode.prototype.createTextEditor = function(graphcanvas, localpos) {
    // Remove any existing editor
    if (this.textEditor) {
        this.textEditor.remove();
        this.textEditor = null;
    }
    
    // Create textarea element
    const textarea = document.createElement('textarea');
    textarea.value = this.properties.task_description;
    textarea.style.position = 'absolute';
    textarea.style.zIndex = '1000';
    textarea.style.width = (this.size[0] - 20) + 'px';
    textarea.style.height = '80px';
    textarea.style.fontSize = '12px';
    textarea.style.fontFamily = 'Arial, sans-serif';
    textarea.style.border = '2px solid #8a5cf6';
    textarea.style.borderRadius = '4px';
    textarea.style.padding = '5px';
    textarea.style.backgroundColor = '#2a2a3a';
    textarea.style.color = '#ffffff';
    textarea.style.resize = 'none';
    textarea.style.outline = 'none';
    textarea.style.cursor = 'text';
    textarea.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)';
    
    // Position the textarea over the node
    const canvasRect = graphcanvas.canvas.getBoundingClientRect();
    const nodePos = this.pos;
    const scale = graphcanvas.ds.scale;
    const offset = graphcanvas.ds.offset;
    
    const screenX = (nodePos[0] + 10) * scale + offset[0] + canvasRect.left;
    const screenY = (nodePos[1] + 60) * scale + offset[1] + canvasRect.top;
    
    textarea.style.left = screenX + 'px';
    textarea.style.top = screenY + 'px';
    textarea.style.transform = `scale(${scale})`;
    textarea.style.transformOrigin = 'top left';
    
    // Add to document
    document.body.appendChild(textarea);
    textarea.focus();
    
    // Set cursor position based on click location if provided
    if (localpos) {
        const clickX = localpos[0] - 10; // Relative to text area
        const clickY = localpos[1] - 60;
        
        // Simple approximation of cursor position
        const charWidth = 7; // Approximate character width
        const lineHeight = 16; // Approximate line height
        const line = Math.floor(clickY / lineHeight);
        const col = Math.floor(clickX / charWidth);
        
        // Calculate position in text
        const lines = textarea.value.split('\n');
        let position = 0;
        for (let i = 0; i < line && i < lines.length; i++) {
            position += lines[i].length + 1; // +1 for newline
        }
        if (line < lines.length) {
            position += Math.min(col, lines[line].length);
        }
        
        setTimeout(() => {
            textarea.setSelectionRange(position, position);
        }, 0);
    } else {
        textarea.select();
    }
    
    this.textEditor = textarea;
    
    // Handle saving the text
    const saveText = () => {
        this.properties.task_description = textarea.value;
        if (this.taskWidget) {
            this.taskWidget.value = textarea.value;
        }
        this.setOutputData(0, textarea.value);
        textarea.remove();
        this.textEditor = null;
        if (graphcanvas) {
            graphcanvas.setDirty(true);
        }
    };
    
    // Save on blur or Enter key
    textarea.addEventListener('blur', () => {
        saveText();
        // Restore default cursor
        if (graphcanvas.canvas) {
            graphcanvas.canvas.style.cursor = 'default';
        }
    });
    
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            saveText();
            // Restore default cursor
            if (graphcanvas.canvas) {
                graphcanvas.canvas.style.cursor = 'default';
            }
        }
        if (e.key === 'Escape') {
            textarea.remove();
            this.textEditor = null;
            // Restore default cursor
            if (graphcanvas.canvas) {
                graphcanvas.canvas.style.cursor = 'default';
            }
        }
        e.stopPropagation();
    });
    
    // Prevent the textarea from interfering with graph interactions
    textarea.addEventListener('mousedown', function(e) {
        e.stopPropagation();
    });
};

TaskInputNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    const statusColors = {
        "ready": "#4CAF50",
        "running": "#FF9800",
        "stopped": "#f44336"
    };
    
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Status indicator
    ctx.fillStyle = statusColors[this.properties.status] || "#666";
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Task icon
    ctx.fillStyle = "#8a5cf6";
    ctx.fillRect(10, 30, 20, 20);
    
    // Status text
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Status: ${this.properties.status}`, 10, 50);
    
    // Text area background (clickable area)
    ctx.fillStyle = "#1a1a2a";
    ctx.fillRect(10, 60, this.size[0] - 20, 80);
    
    // Text area border with subtle glow effect for editability
    ctx.strokeStyle = "#8a5cf6";
    ctx.lineWidth = 2;
    ctx.strokeRect(10, 60, this.size[0] - 20, 80);
    
    // Add a subtle inner glow to indicate editability
    ctx.strokeStyle = "rgba(138, 92, 246, 0.3)";
    ctx.lineWidth = 1;
    ctx.strokeRect(11, 61, this.size[0] - 22, 78);
    
    // Add a small text cursor icon in the top-right corner of the text area
    ctx.fillStyle = "#8a5cf6";
    ctx.font = "12px Arial";
    ctx.fillText("✎", this.size[0] - 25, 75);
    
    // Display current task text (truncated if too long)
    ctx.fillStyle = "#ffffff";
    ctx.font = "11px Arial";
    const taskText = this.properties.task_description || "Enter a task for the campfires to process...";
    const maxWidth = this.size[0] - 30;
    const lines = this.wrapText(ctx, taskText, maxWidth);
    
    for (let i = 0; i < Math.min(lines.length, 5); i++) {
        ctx.fillText(lines[i], 15, 75 + i * 14);
    }
    
    // Show "..." if text is truncated
    if (lines.length > 5) {
        ctx.fillStyle = "#aaa";
        ctx.fillText("...", 15, 75 + 5 * 14);
    }
    
    // Instruction text
    ctx.fillStyle = "#aaa";
    ctx.font = "10px Arial";
    ctx.fillText("Click in the text area to edit • Ctrl+Enter to save", 10, this.size[1] - 10);
};

TaskInputNode.prototype.wrapText = function(ctx, text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = words[0] || '';
    
    for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = ctx.measureText(currentLine + " " + word).width;
        if (width < maxWidth) {
            currentLine += " " + word;
        } else {
            lines.push(currentLine);
            currentLine = word;
        }
    }
    if (currentLine) {
        lines.push(currentLine);
    }
    return lines;
};

// View Mode Node - replaces view mode dropdown
function ViewModeNode() {
    this.addOutput("view_mode", "string");
    this.addProperty("current_mode", "overview");
    this.size = [200, 120];
    
    this.addWidget("combo", "View Mode", this.properties.current_mode, (v) => {
        this.properties.current_mode = v;
        this.setOutputData(0, v);
    }, { values: ["overview", "campfires", "campers"] });
}

ViewModeNode.title = "View Mode";
ViewModeNode.desc = "Controls the current view mode";

ViewModeNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#4ade80";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Mode: ${this.properties.current_mode}`, 10, 70);
};

// Filter Node - replaces filter input
function FilterNode() {
    this.addOutput("filter_text", "string");
    this.addProperty("filter", "");
    this.size = [200, 100];
    
    this.addWidget("text", "Filter", this.properties.filter, (v) => {
        this.properties.filter = v;
        this.setOutputData(0, v);
    });
}

FilterNode.title = "Filter";
FilterNode.desc = "Filters nodes based on text input";

FilterNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#3a2a3a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Filter: ${this.properties.filter || "None"}`, 10, 70);
};

// Zoom Control Node - replaces zoom buttons
function ZoomControlNode() {
    this.addOutput("zoom_in", "trigger");
    this.addOutput("zoom_out", "trigger");
    this.addOutput("reset_view", "trigger");
    this.addProperty("zoom_level", 1.0);
    this.size = [180, 140];
    
    this.addWidget("button", "Zoom In", null, () => {
        this.properties.zoom_level = Math.min(this.properties.zoom_level * 1.2, 3.0);
        this.triggerSlot(0);
    });
    
    this.addWidget("button", "Zoom Out", null, () => {
        this.properties.zoom_level = Math.max(this.properties.zoom_level / 1.2, 0.3);
        this.triggerSlot(1);
    });
    
    this.addWidget("button", "Reset", null, () => {
        this.properties.zoom_level = 1.0;
        this.triggerSlot(2);
    });
}

ZoomControlNode.title = "Zoom Control";
ZoomControlNode.desc = "Controls canvas zoom level";

ZoomControlNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#3a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#06b6d4";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Zoom: ${(this.properties.zoom_level * 100).toFixed(0)}%`, 10, 70);
};

// Display Options Node - replaces checkboxes
function DisplayOptionsNode() {
    this.addOutput("show_connections", "boolean");
    this.addOutput("show_torch_flow", "boolean");
    this.addOutput("auto_refresh", "boolean");
    this.addProperty("connections", true);
    this.addProperty("torch_flow", true);
    this.addProperty("refresh", true);
    this.size = [220, 160];
    
    this.addWidget("toggle", "Show Connections", this.properties.connections, (v) => {
        this.properties.connections = v;
        this.setOutputData(0, v);
    });
    
    this.addWidget("toggle", "Show Torch Flow", this.properties.torch_flow, (v) => {
        this.properties.torch_flow = v;
        this.setOutputData(1, v);
    });
    
    this.addWidget("toggle", "Auto Refresh", this.properties.refresh, (v) => {
        this.properties.refresh = v;
        this.setOutputData(2, v);
    });
}

DisplayOptionsNode.title = "Display Options";
DisplayOptionsNode.desc = "Controls display settings";

DisplayOptionsNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Connections: ${this.properties.connections ? "On" : "Off"}`, 10, 70);
    ctx.fillText(`Torch Flow: ${this.properties.torch_flow ? "On" : "Off"}`, 10, 85);
    ctx.fillText(`Auto Refresh: ${this.properties.refresh ? "On" : "Off"}`, 10, 100);
};

// Node Details Display Node - replaces node info panel
function NodeDetailsNode() {
    this.addInput("selected_node", "object");
    this.addProperty("node_title", "No Selection");
    this.addProperty("node_details", "Select a node to view details");
    this.addProperty("show_gamification", true);
    this.size = [320, 180]; // Wider and shorter for better proportions
}

NodeDetailsNode.title = "Node Details";
NodeDetailsNode.desc = "Displays details of selected nodes";

NodeDetailsNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a2a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Get selected node data from input
    const selectedNode = this.getInputData(0);
    
    // Draw icon with gamification glow
    let iconColor = "#f59e0b";
    if (selectedNode && selectedNode.properties) {
        const gameEngine = window.CampfireGameEngine;
        if (gameEngine && selectedNode.properties.efficiency) {
            const glowIntensity = gameEngine.calculateGlowIntensity(selectedNode.properties.efficiency);
            if (glowIntensity > 0.5) {
                // Draw glow effect
                ctx.shadowColor = "#ffdd44";
                ctx.shadowBlur = 10;
                iconColor = "#ffdd44";
            }
        }
    }
    
    ctx.fillStyle = iconColor;
    ctx.fillRect(10, 30, 20, 20);
    ctx.shadowBlur = 0; // Reset shadow
    
    // Draw title
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(this.properties.node_title, 10, 70);
    
    let yPos = 85;
    
    // Draw basic details
    ctx.font = "10px Arial";
    const details = this.properties.node_details;
    const lines = this.wrapText(ctx, details, this.size[0] - 20);
    for (let i = 0; i < Math.min(lines.length, 3); i++) {
        ctx.fillText(lines[i], 10, yPos + i * 12);
    }
    yPos += Math.min(lines.length, 3) * 12 + 10;
    
    // Draw gamification metrics if enabled and node is selected
    if (this.properties.show_gamification && selectedNode && selectedNode.properties) {
        const props = selectedNode.properties;
        
        // Draw separator line
        ctx.strokeStyle = "#555";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(10, yPos);
        ctx.lineTo(this.size[0] - 10, yPos);
        ctx.stroke();
        yPos += 15;
        
        // Gamification header
        ctx.fillStyle = "#ffdd44";
        ctx.font = "11px Arial";
        ctx.fillText("🎮 Gamification Stats", 10, yPos);
        yPos += 15;
        
        ctx.fillStyle = "#ffffff";
        ctx.font = "9px Arial";
        
        // Display relevant metrics based on node type
        if (props.temperature !== undefined) {
            ctx.fillText(`🔥 Temperature: ${Math.round(props.temperature)}°`, 10, yPos);
            yPos += 12;
        }
        
        if (props.efficiency !== undefined) {
            ctx.fillText(`⚡ Efficiency: ${Math.round(props.efficiency)}%`, 10, yPos);
            yPos += 12;
        }
        
        if (props.happiness !== undefined) {
            const moodEmoji = props.happiness > 80 ? "😊" : props.happiness > 60 ? "😐" : "😟";
            ctx.fillText(`${moodEmoji} Happiness: ${Math.round(props.happiness)}%`, 10, yPos);
            yPos += 12;
        }
        
        if (props.energy !== undefined) {
            ctx.fillText(`🔋 Energy: ${Math.round(props.energy)}%`, 10, yPos);
            yPos += 12;
        }
        
        if (props.prosperity !== undefined) {
            ctx.fillText(`🌟 Prosperity: ${Math.round(props.prosperity)}%`, 10, yPos);
            yPos += 12;
        }
        
        if (props.experience_points !== undefined) {
            ctx.fillText(`🏆 XP: ${props.experience_points}`, 10, yPos);
            yPos += 12;
        }
        
        // Show achievements if any
        const gameEngine = window.CampfireGameEngine;
        if (gameEngine && gameEngine.nodeAchievements) {
            const nodeId = selectedNode.id || selectedNode.title;
            const nodeAchievements = gameEngine.nodeAchievements[nodeId];
            if (nodeAchievements && nodeAchievements.size > 0) {
                ctx.fillStyle = "#ffdd44";
                ctx.fillText(`🏅 Achievements: ${nodeAchievements.size}`, 10, yPos);
            }
        }
    }
};

NodeDetailsNode.prototype.wrapText = function(ctx, text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = words[0];
    
    for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = ctx.measureText(currentLine + " " + word).width;
        if (width < maxWidth) {
            currentLine += " " + word;
        } else {
            lines.push(currentLine);
            currentLine = word;
        }
    }
    lines.push(currentLine);
    return lines;
};

// Status Legend Node - replaces legend panel
function StatusLegendNode() {
    this.addProperty("show_legend", true);
    this.size = [180, 140];
}

StatusLegendNode.title = "Status Legend";
StatusLegendNode.desc = "Shows status indicator meanings";

StatusLegendNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a2a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    const statuses = [
        { name: "Active", color: "#4CAF50" },
        { name: "Busy", color: "#FF9800" },
        { name: "Error", color: "#f44336" },
        { name: "Offline", color: "#666666" }
    ];
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText("Legend", 10, 30);
    
    ctx.font = "10px Arial";
    statuses.forEach((status, i) => {
        const y = 50 + i * 20;
        ctx.fillStyle = status.color;
        ctx.fillRect(10, y - 8, 10, 10);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(status.name, 25, y);
    });
};

// Valley Node - represents a valley in the system (top of hierarchy)
function ValleyNode() {
    this.addOutput("dock_connection", "dock");
    this.addOutput("campfire_connection", "campfire");
    this.addProperty("name", "Valley");
    this.addProperty("status", "active");
    this.addProperty("total_campfires", 0);
    this.addProperty("total_campers", 0);
    this.addProperty("dock_status", "active");
    this.addProperty("federation_status", "disconnected");
    
    // Gamification properties
    this.addProperty("prosperity", 65);
    this.addProperty("growth_stage", "growing");
    this.addProperty("active_campfires", 0);
    this.addProperty("avg_efficiency", 75);
    this.addProperty("total_tasks", 0);
    this.addProperty("valley_level", 1);
    this.addProperty("experience_points", 0);
    
    this.size = [260, 180]; // Initial size, will be auto-adjusted
    
    // Auto-size the node based on content after a short delay to ensure properties are set
    setTimeout(() => {
        this.autoSizeNode(this.onDrawBackground, 260, 15);
    }, 100);
}

ValleyNode.title = "Valley";
ValleyNode.desc = "Represents a valley in CampfireValley";

// Apply dynamic sizing mixin to Valley node
Object.assign(ValleyNode.prototype, DynamicSizingMixin);

ValleyNode.prototype.onExecute = function() {
    const valleyData = {
        name: this.properties.name,
        status: this.properties.status,
        total_campfires: this.properties.total_campfires,
        total_campers: this.properties.total_campers,
        dock_status: this.properties.dock_status,
        federation_status: this.properties.federation_status
    };
    this.setOutputData(0, valleyData); // dock connection
    this.setOutputData(1, valleyData); // campfire connection
};

ValleyNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    // Calculate gamification values
    const gameEngine = window.CampfireGameEngine;
    if (gameEngine) {
        this.properties.prosperity = gameEngine.calculateValleyProsperity(
            this.properties.active_campfires,
            this.properties.total_campfires,
            this.properties.avg_efficiency,
            this.properties.total_tasks
        );
        this.properties.growth_stage = gameEngine.getValleyGrowthStage(this.properties.prosperity);
    }
    
    // Background with prosperity-based sky color
    let bgColor = "#2a4d3a";
    if (gameEngine) {
        const skyColor = gameEngine.getSkyColor(this.properties.prosperity);
        bgColor = `rgb(${Math.floor(skyColor.r * 0.3)}, ${Math.floor(skyColor.g * 0.4)}, ${Math.floor(skyColor.b * 0.3)})`;
    }
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw valley landscape with growth elements
    const baseGreen = this.properties.prosperity > 70 ? "#5a9c69" : "#4a7c59";
    ctx.fillStyle = baseGreen;
    ctx.fillRect(10, 30, this.size[0] - 20, 25);
    
    // Draw trees based on prosperity
    if (gameEngine) {
        const visualElements = gameEngine.getValleyVisualElements(this.properties.prosperity);
        ctx.fillStyle = "#2d5a3d";
        for (let i = 0; i < visualElements.treeCount; i++) {
            const x = 20 + (i * 30);
            if (x < this.size[0] - 30) {
                ctx.fillRect(x, 25, 8, 15); // Tree trunk
                ctx.fillStyle = "#4a7c59";
                ctx.fillRect(x - 3, 20, 14, 10); // Tree crown
                ctx.fillStyle = "#2d5a3d";
            }
        }
        
        // Draw flowers based on prosperity
        ctx.fillStyle = "#ff6b9d";
        for (let i = 0; i < visualElements.flowerCount; i++) {
            const x = 15 + (i * 25);
            const y = 45;
            if (x < this.size[0] - 15) {
                ctx.fillRect(x, y, 3, 3);
            }
        }
    }
    
    // Draw prosperity bar
    if (gameEngine) {
        gameEngine.drawProgressBar(ctx, 10, 60, this.size[0] - 20, 8, 
                                  this.properties.prosperity, 100, "#4CAF50");
    }
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw growth stage indicator
    const stageEmojis = {
        "struggling": "🌱",
        "developing": "🌿", 
        "growing": "🌳",
        "thriving": "🌲",
        "flourishing": "🌟"
    };
    const stageEmoji = stageEmojis[this.properties.growth_stage] || "🌱";
    ctx.font = "16px Arial";
    ctx.fillText(stageEmoji, this.size[0] - 25, 35);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "11px Arial";
    ctx.fillText(`Campfires: ${this.properties.total_campfires}`, 10, 85);
    ctx.fillText(`Campers: ${this.properties.total_campers}`, 10, 100);
    ctx.fillText(`Dock: ${this.properties.dock_status}`, 10, 115);
    
    // Gamification metrics
    ctx.fillStyle = "#ffdd44";
    ctx.font = "10px Arial";
    ctx.fillText(`🌟 Prosperity: ${Math.round(this.properties.prosperity)}%`, 10, 135);
    ctx.fillText(`📈 Stage: ${this.properties.growth_stage}`, 10, 150);
    ctx.fillText(`🏆 Level: ${this.properties.valley_level}`, 10, 165);
};

// Dock Node - represents the valley's dock gateway
function DockNode() {
    this.addInput("valley_connection", "dock");
    this.addOutput("dockmaster_connection", "dockmaster");
    this.addOutput("sanitizer_connection", "sanitizer");
    this.addOutput("justice_connection", "justice");
    this.addProperty("name", "Dock Gateway");
    this.addProperty("status", "active");
    this.addProperty("mode", "private");
    this.addProperty("torch_throughput", 0);
    this.addProperty("security_level", "standard");
    this.size = [240, 160]; // Initial size
    
    // Apply dynamic sizing with overlap resolution after properties are set
    setTimeout(() => {
        this.autoSizeNodeWithOverlapResolution(this.onDrawBackground, 260, 15);
    }, 100);
}

DockNode.title = "Dock";
DockNode.desc = "Represents the valley's dock gateway";

// Add dynamic sizing capabilities
Object.assign(DockNode.prototype, DynamicSizingMixin);

DockNode.prototype.onExecute = function() {
    const dockData = {
        name: this.properties.name,
        status: this.properties.status,
        mode: this.properties.mode,
        torch_throughput: this.properties.torch_throughput,
        security_level: this.properties.security_level
    };
    this.setOutputData(0, dockData); // dockmaster
    this.setOutputData(1, dockData); // sanitizer
    this.setOutputData(2, dockData); // justice
};

DockNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw dock icon
    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(10, 30, this.size[0] - 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Mode: ${this.properties.mode}`, 10, 70);
    ctx.fillText(`Throughput: ${this.properties.torch_throughput}`, 10, 85);
    ctx.fillText(`Security: ${this.properties.security_level}`, 10, 100);
};

// Dockmaster Campfire Node - handles torch loading, routing, and packing
function DockmasterCampfireNode() {
    this.addInput("dock_connection", "dockmaster");
    this.addOutput("loader_connection", "camper");
    this.addOutput("router_connection", "camper");
    this.addOutput("packer_connection", "camper");
    this.addProperty("name", "Dockmaster");
    this.addProperty("status", "active");
    this.addProperty("torch_queue", 0);
    this.addProperty("routing_efficiency", 95);
    this.size = [220, 140];
}

DockmasterCampfireNode.title = "Dockmaster Campfire";
DockmasterCampfireNode.desc = "Handles torch loading, routing, and packing";

DockmasterCampfireNode.prototype.onExecute = function() {
    const dockmasterData = {
        name: this.properties.name,
        status: this.properties.status,
        torch_queue: this.properties.torch_queue,
        routing_efficiency: this.properties.routing_efficiency
    };
    this.setOutputData(0, dockmasterData); // loader
    this.setOutputData(1, dockmasterData); // router
    this.setOutputData(2, dockmasterData); // packer
};

DockmasterCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon
    ctx.fillStyle = "#ff6b35";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Queue: ${this.properties.torch_queue}`, 10, 70);
    ctx.fillText(`Efficiency: ${this.properties.routing_efficiency}%`, 10, 85);
};

// Sanitizer Campfire Node - handles content security and sanitization
function SanitizerCampfireNode() {
    this.addInput("dock_connection", "sanitizer");
    this.addOutput("scanner_connection", "camper");
    this.addOutput("filter_connection", "camper");
    this.addOutput("quarantine_connection", "camper");
    this.addProperty("name", "Sanitizer");
    this.addProperty("status", "active");
    this.addProperty("threats_detected", 0);
    this.addProperty("quarantine_count", 0);
    this.size = [220, 140];
}

SanitizerCampfireNode.title = "Sanitizer Campfire";
SanitizerCampfireNode.desc = "Handles content security and sanitization";

SanitizerCampfireNode.prototype.onExecute = function() {
    const sanitizerData = {
        name: this.properties.name,
        status: this.properties.status,
        threats_detected: this.properties.threats_detected,
        quarantine_count: this.properties.quarantine_count
    };
    this.setOutputData(0, sanitizerData); // scanner
    this.setOutputData(1, sanitizerData); // filter
    this.setOutputData(2, sanitizerData); // quarantine
};

SanitizerCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon with security theme
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Threats: ${this.properties.threats_detected}`, 10, 70);
    ctx.fillText(`Quarantine: ${this.properties.quarantine_count}`, 10, 85);
};

// Justice Campfire Node - handles governance and compliance
function JusticeCampfireNode() {
    this.addInput("dock_connection", "justice");
    this.addOutput("detector_connection", "camper");
    this.addOutput("enforcer_connection", "camper");
    this.addOutput("governor_connection", "camper");
    this.addProperty("name", "Justice");
    this.addProperty("status", "active");
    this.addProperty("violations_detected", 0);
    this.addProperty("sanctions_applied", 0);
    this.size = [220, 140];
}

JusticeCampfireNode.title = "Justice Campfire";
JusticeCampfireNode.desc = "Handles governance and compliance";

JusticeCampfireNode.prototype.onExecute = function() {
    const justiceData = {
        name: this.properties.name,
        status: this.properties.status,
        violations_detected: this.properties.violations_detected,
        sanctions_applied: this.properties.sanctions_applied
    };
    this.setOutputData(0, justiceData); // detector
    this.setOutputData(1, justiceData); // enforcer
    this.setOutputData(2, justiceData); // governor
};

JusticeCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon with justice theme
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Violations: ${this.properties.violations_detected}`, 10, 70);
    ctx.fillText(`Sanctions: ${this.properties.sanctions_applied}`, 10, 85);
};

// Regular Campfire Node - represents standard campfires from config
function CampfireNode() {
    this.addInput("valley_connection", "campfire");
    this.addOutput("camper_connection", "camper");
    this.addProperty("name", "Campfire");
    this.addProperty("type", "standard");
    this.addProperty("status", "active");
    this.addProperty("camper_count", 0);
    this.addProperty("torch_queue", 0);
    this.addProperty("config_source", "config file");
    
    // Gamification properties
    this.addProperty("efficiency", 75);
    this.addProperty("usage_frequency", 50);
    this.addProperty("tasks_completed", 0);
    this.addProperty("temperature", 60);
    this.addProperty("glow_intensity", 0.6);
    this.addProperty("experience_points", 0);
    
    this.size = [240, 160]; // Initial size with extra height for content
    
    // Apply dynamic sizing with overlap resolution after properties are set
    setTimeout(() => {
        this.autoSizeNodeWithOverlapResolution(this.onDrawBackground, 240, 15);
    }, 100);
}

CampfireNode.title = "Campfire";
CampfireNode.desc = "Represents a campfire processing tasks";

// Add dynamic sizing capabilities
Object.assign(CampfireNode.prototype, DynamicSizingMixin);

CampfireNode.prototype.onExecute = function() {
    this.setOutputData(0, {
        name: this.properties.name,
        type: this.properties.type,
        status: this.properties.status,
        camper_count: this.properties.camper_count,
        torch_queue: this.properties.torch_queue,
        config_source: this.properties.config_source
    });
};

CampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    // Calculate gamification values
    const gameEngine = window.CampfireGameEngine;
    if (gameEngine) {
        this.properties.temperature = gameEngine.calculateCampfireTemperature(
            this.properties.efficiency, 
            this.properties.usage_frequency, 
            this.properties.torch_queue
        );
        this.properties.glow_intensity = gameEngine.getCampfireGlowIntensity(this.properties.temperature);
    }
    
    // Background with subtle glow
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw glow effect around the campfire
    if (gameEngine && this.properties.temperature > 30) {
        const glowColor = gameEngine.getCampfireColor(this.properties.temperature);
        gameEngine.drawGlowEffect(ctx, this.size[0]/2 - 15, 25, 30, 30, 
                                 this.properties.glow_intensity, glowColor);
    }
    
    // Draw campfire with flame effect
    if (gameEngine) {
        gameEngine.drawFlameEffect(ctx, this.size[0]/2 - 15, 25, 30, 30, 
                                  this.properties.temperature, this.properties.status === "active");
    } else {
        // Fallback campfire icon
        ctx.fillStyle = "#ff6b35";
        ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    }
    
    // Draw temperature indicator
    const tempColor = this.properties.temperature > 70 ? "#ff4444" : 
                     this.properties.temperature > 40 ? "#ff8844" : "#4488ff";
    ctx.fillStyle = tempColor;
    ctx.fillRect(this.size[0] - 25, 10, 15, 8);
    
    // Draw status indicator
    const statusColors = {
        "idle": "#4CAF50",
        "busy": "#FF9800", 
        "error": "#f44336",
        "active": "#4CAF50"
    };
    ctx.fillStyle = statusColors[this.properties.status] || "#666";
    ctx.fillRect(this.size[0] - 20, 22, 10, 10);
    
    // Draw text with gamification info
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Status: ${this.properties.status}`, 10, 70);
    ctx.fillText(`Campers: ${this.properties.camper_count}`, 10, 85);
    ctx.fillText(`Queue: ${this.properties.torch_queue}`, 10, 100);
    
    // Gamification metrics
    ctx.fillStyle = "#ffdd44";
    ctx.font = "9px Arial";
    ctx.fillText(`🔥 Temp: ${Math.round(this.properties.temperature)}°`, 10, 115);
    ctx.fillText(`⚡ Eff: ${this.properties.efficiency}%`, 10, 130);
    ctx.fillText(`⭐ XP: ${this.properties.experience_points}`, 10, 145);
};

// Specialized Camper Nodes for Dock Campfires
function LoaderCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Loader");
    this.addProperty("status", "active");
    this.addProperty("torches_loaded", 0);
    this.addProperty("validation_rate", 100);
    
    // Gamification properties
    this.addProperty("happiness", 75);
    this.addProperty("energy", 80);
    this.addProperty("tasks_completed", 0);
    this.addProperty("cpu_usage", 25);
    this.addProperty("memory_usage", 30);
    this.addProperty("error_rate", 0.02);
    
    this.size = [220, 100]; // Wider and shorter for better proportions
}

LoaderCamperNode.title = "Loader Camper";
LoaderCamperNode.desc = "Loads and validates torches";

LoaderCamperNode.prototype.onExecute = function() {
    // Loader camper processing logic
};

LoaderCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    // Calculate gamification values
    const gameEngine = window.CampfireGameEngine;
    if (gameEngine) {
        this.properties.happiness = gameEngine.calculateCamperHappiness(
            this.properties.tasks_completed,
            this.properties.cpu_usage,
            this.properties.memory_usage,
            this.properties.error_rate
        );
        this.properties.energy = gameEngine.getCamperEnergyLevel(
            this.properties.happiness,
            this.properties.status === "active" ? "loading" : "idle"
        );
    }
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw loader icon with energy glow
    if (gameEngine && this.properties.energy > 60) {
        const glowColor = { r: 16, g: 185, b: 129 };
        gameEngine.drawGlowEffect(ctx, this.size[0]/2 - 12, 21, 24, 24, 
                                 this.properties.energy / 100, glowColor);
    }
    
    ctx.fillStyle = "#10b981";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw happiness emoji
    const moodEmoji = gameEngine ? gameEngine.getCamperMoodEmoji(this.properties.happiness) : "🙂";
    ctx.font = "12px Arial";
    ctx.fillText(moodEmoji, this.size[0] - 25, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 25, 10, 10);
    
    // Draw energy bar
    if (gameEngine) {
        gameEngine.drawProgressBar(ctx, 10, 45, this.size[0] - 20, 6, 
                                  this.properties.energy, 100, "#4CAF50");
    }
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Loaded: ${this.properties.torches_loaded}`, 10, 65);
    ctx.fillText(`Rate: ${this.properties.validation_rate}%`, 10, 80);
    
    // Gamification metrics
    ctx.fillStyle = "#ffdd44";
    ctx.font = "9px Arial";
    ctx.fillText(`😊 ${Math.round(this.properties.happiness)}%`, 10, 95);
    ctx.fillText(`⚡ ${Math.round(this.properties.energy)}%`, 10, 110);
};

function RouterCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Router");
    this.addProperty("status", "active");
    this.addProperty("routes_processed", 0);
    this.addProperty("routing_accuracy", 98);
    this.size = [180, 100];
}

RouterCamperNode.title = "Router Camper";
RouterCamperNode.desc = "Routes torches to destinations";

RouterCamperNode.prototype.onExecute = function() {
    // Router camper processing logic
};

RouterCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw router icon
    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Routed: ${this.properties.routes_processed}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.routing_accuracy}%`, 10, 75);
};

function PackerCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Packer");
    this.addProperty("status", "active");
    this.addProperty("torches_packed", 0);
    this.addProperty("compression_ratio", 75);
    this.size = [180, 100];
}

PackerCamperNode.title = "Packer Camper";
PackerCamperNode.desc = "Packs torches for transport";

PackerCamperNode.prototype.onExecute = function() {
    // Packer camper processing logic
};

PackerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw packer icon
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Packed: ${this.properties.torches_packed}`, 10, 60);
    ctx.fillText(`Ratio: ${this.properties.compression_ratio}%`, 10, 75);
};

function ScannerCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Scanner");
    this.addProperty("status", "active");
    this.addProperty("scans_completed", 0);
    this.addProperty("threats_found", 0);
    this.size = [180, 100];
}

ScannerCamperNode.title = "Scanner Camper";
ScannerCamperNode.desc = "Scans content for threats";

ScannerCamperNode.prototype.onExecute = function() {
    // Scanner camper processing logic
};

ScannerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw scanner icon
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Scanned: ${this.properties.scans_completed}`, 10, 60);
    ctx.fillText(`Threats: ${this.properties.threats_found}`, 10, 75);
};

function FilterCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Filter");
    this.addProperty("status", "active");
    this.addProperty("content_filtered", 0);
    this.addProperty("filter_accuracy", 99);
    this.size = [180, 100];
}

FilterCamperNode.title = "Filter Camper";
FilterCamperNode.desc = "Filters malicious content";

FilterCamperNode.prototype.onExecute = function() {
    // Filter camper processing logic
};

FilterCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw filter icon
    ctx.fillStyle = "#f97316";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Filtered: ${this.properties.content_filtered}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.filter_accuracy}%`, 10, 75);
};

function QuarantineCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Quarantine");
    this.addProperty("status", "active");
    this.addProperty("items_quarantined", 0);
    this.addProperty("quarantine_capacity", 100);
    this.size = [180, 100];
}

QuarantineCamperNode.title = "Quarantine Camper";
QuarantineCamperNode.desc = "Quarantines suspicious content";

QuarantineCamperNode.prototype.onExecute = function() {
    // Quarantine camper processing logic
};

QuarantineCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw quarantine icon
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Quarantined: ${this.properties.items_quarantined}`, 10, 60);
    ctx.fillText(`Capacity: ${this.properties.quarantine_capacity}`, 10, 75);
};

function DetectorCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Detector");
    this.addProperty("status", "active");
    this.addProperty("violations_detected", 0);
    this.addProperty("detection_accuracy", 97);
    this.size = [180, 100];
}

DetectorCamperNode.title = "Detector Camper";
DetectorCamperNode.desc = "Detects policy violations";

DetectorCamperNode.prototype.onExecute = function() {
    // Detector camper processing logic
};

DetectorCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw detector icon
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Detected: ${this.properties.violations_detected}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.detection_accuracy}%`, 10, 75);
};

function EnforcerCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Enforcer");
    this.addProperty("status", "active");
    this.addProperty("sanctions_applied", 0);
    this.addProperty("enforcement_rate", 100);
    this.size = [180, 100];
}

EnforcerCamperNode.title = "Enforcer Camper";
EnforcerCamperNode.desc = "Enforces policies and sanctions";

EnforcerCamperNode.prototype.onExecute = function() {
    // Enforcer camper processing logic
};

EnforcerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw enforcer icon
    ctx.fillStyle = "#7c3aed";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Sanctions: ${this.properties.sanctions_applied}`, 10, 60);
    ctx.fillText(`Rate: ${this.properties.enforcement_rate}%`, 10, 75);
};

function GovernorCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Governor");
    this.addProperty("status", "active");
    this.addProperty("policies_managed", 0);
    this.addProperty("compliance_rate", 95);
    this.size = [180, 100];
}

GovernorCamperNode.title = "Governor Camper";
GovernorCamperNode.desc = "Manages governance policies";

GovernorCamperNode.prototype.onExecute = function() {
    // Governor camper processing logic
};

GovernorCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw governor icon
    ctx.fillStyle = "#6366f1";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Policies: ${this.properties.policies_managed}`, 10, 60);
    ctx.fillText(`Compliance: ${this.properties.compliance_rate}%`, 10, 75);
};

// Generic Camper Node - for regular campfire campers
function CamperNode() {
    this.addInput("campfire_connection", "camper");
    this.addProperty("name", "Camper");
    this.addProperty("type", "worker");
    this.addProperty("status", "active");
    this.addProperty("current_task", "idle");
    this.addProperty("tasks_completed", 0);
    this.size = [180, 120];
}

CamperNode.title = "Camper";
CamperNode.desc = "Represents a camper in the system";

CamperNode.prototype.onExecute = function() {
    this.setOutputData(0, {
        name: this.properties.name,
        type: this.properties.type,
        status: this.properties.status,
        current_task: this.properties.current_task,
        tasks_completed: this.properties.tasks_completed
    });
};

CamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw camper icon
    ctx.fillStyle = "#5a9fd4";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Task: ${this.properties.current_task}`, 10, 60);
    ctx.fillText(`Completed: ${this.properties.tasks_completed}`, 10, 75);
};

// WebSocket Data Node - handles real-time data
function WebSocketDataNode() {
    this.addOutput("valley_data", "valley");
    this.addOutput("campfire_data", "campfire");
    this.addOutput("camper_data", "camper");
    this.addOutput("connection_status", "string");
    this.addProperty("connection_status", "disconnected");
    this.addProperty("auto_refresh", true);
    this.size = [200, 120];
}

WebSocketDataNode.title = "WebSocket Data";
WebSocketDataNode.desc = "Handles real-time data from WebSocket";

WebSocketDataNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw connection status
    const statusColor = this.properties.connection_status === "connected" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw WebSocket icon
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(10, 30, 20, 20);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Status: ${this.properties.connection_status}`, 10, 70);
    ctx.fillText(`Auto Refresh: ${this.properties.auto_refresh ? "On" : "Off"}`, 10, 85);
};

// Add dynamic sizing capabilities to TaskInputNode
Object.assign(TaskInputNode.prototype, DynamicSizingMixin);

// UI Panel Node - contains all UI controls in a single draggable panel
function UIControlPanelNode() {
    this.size = [360, 780]; // Wide enough for controls, tall enough for all UI elements
    this.properties = {
        title: "UI Controls",
        collapsed: false
    };
    
    // Store references to internal UI elements
    this.internalControls = {
        websocket: null,
        taskInput: null,
        viewMode: null,
        filter: null,
        zoomControl: null,
        displayOptions: null,
        nodeDetails: null,
        statusLegend: null
    };
    
    // Initialize internal controls
    this.initializeInternalControls();
    
    // Add collapse/expand button
    this.addWidget("button", this.properties.collapsed ? "▶ Expand" : "▼ Collapse", null, () => {
        this.properties.collapsed = !this.properties.collapsed;
        this.updatePanelSize();
        this.widgets[0].name = this.properties.collapsed ? "▶ Expand" : "▼ Collapse";
    });
    
    // Ensure proper initial size
    this.updatePanelSize();
}

UIControlPanelNode.title = "UI Control Panel";
UIControlPanelNode.desc = "Draggable panel containing all UI controls";

UIControlPanelNode.prototype.initializeInternalControls = function() {
    // Create internal control data structures
    this.internalControls.websocket = {
        status: "disconnected",
        autoRefresh: false,
        y: 40
    };
    
    this.internalControls.taskInput = {
        text: "Enter a task for the campfires to process...",
        status: "ready",
        y: 120
    };
    
    this.internalControls.viewMode = {
        mode: "hierarchy",
        y: 240
    };
    
    this.internalControls.filter = {
        text: "",
        y: 320
    };
    
    this.internalControls.zoomControl = {
        level: 1.0,
        y: 400
    };
    
    this.internalControls.displayOptions = {
        showLabels: true,
        showConnections: true,
        y: 480
    };
    
    this.internalControls.nodeDetails = {
        selectedNode: null,
        y: 560
    };
    
    this.internalControls.statusLegend = {
        visible: true,
        y: 640
    };
    
    this.internalControls.layoutManagement = {
        y: 720
    };
};

UIControlPanelNode.prototype.updatePanelSize = function() {
    if (this.properties.collapsed) {
        this.size = [360, 60]; // Just show title and expand button
    } else {
        this.size = [360, 860]; // Increased height to accommodate layout management section
    }
    this.setDirtyCanvas(true, true);
};

UIControlPanelNode.prototype.onDrawForeground = function(ctx) {
    if (this.flags.collapsed) return;
    
    // Draw panel background
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw panel border
    ctx.strokeStyle = "#8a5cf6";
    ctx.lineWidth = 2;
    ctx.strokeRect(0, 0, this.size[0], this.size[1]);
    
    // Draw title bar
    ctx.fillStyle = "#8a5cf6";
    ctx.fillRect(0, 0, this.size[0], 30);
    
    // Draw title text
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 14px Arial";
    ctx.fillText(this.properties.title, 10, 20);
    
    if (this.properties.collapsed) return;
    
    // Draw internal controls
    this.drawWebSocketControl(ctx);
    this.drawTaskInputControl(ctx);
    this.drawViewModeControl(ctx);
    this.drawFilterControl(ctx);
    this.drawZoomControl(ctx);
    this.drawDisplayOptionsControl(ctx);
    this.drawNodeDetailsControl(ctx);
    this.drawStatusLegendControl(ctx);
    this.drawLayoutManagementControl(ctx);
};

UIControlPanelNode.prototype.drawWebSocketControl = function(ctx) {
    const y = this.internalControls.websocket.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("WebSocket Connection", 20, y + 15);
    
    // Status indicator
    const statusColor = this.internalControls.websocket.status === "connected" ? "#10b981" : "#ef4444";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 30, y + 5, 10, 10);
    
    // Status text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Status: ${this.internalControls.websocket.status}`, 20, y + 35);
    ctx.fillText(`Auto Refresh: ${this.internalControls.websocket.autoRefresh ? "On" : "Off"}`, 20, y + 50);
};

UIControlPanelNode.prototype.drawTaskInputControl = function(ctx) {
    const y = this.internalControls.taskInput.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 110);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 110);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Task Input", 20, y + 15);
    
    // Text area background
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(20, y + 25, this.size[0] - 40, 50);
    ctx.strokeStyle = "#8a5cf6";
    ctx.strokeRect(20, y + 25, this.size[0] - 40, 50);
    
    // Task text (wrapped)
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    const maxWidth = this.size[0] - 50; // Text area width minus padding
    const lineHeight = 12;
    const maxLines = 3; // Fit within the 50px height text area
    
    const wrappedLines = this.wrapText(ctx, this.internalControls.taskInput.text, maxWidth, maxLines);
    wrappedLines.forEach((line, index) => {
        if (index < maxLines) {
            ctx.fillText(line, 25, y + 40 + (index * lineHeight));
        }
    });
    
    // Buttons
    ctx.fillStyle = "#10b981";
    ctx.fillRect(20, y + 85, 60, 20);
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(90, y + 85, 60, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText("🚀 Start", 25, y + 98);
    ctx.fillText("⏹️ Stop", 95, y + 98);
};

UIControlPanelNode.prototype.drawViewModeControl = function(ctx) {
    const y = this.internalControls.viewMode.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("View Mode", 20, y + 15);
    
    // Current mode
    ctx.font = "10px Arial";
    ctx.fillText(`Current: ${this.internalControls.viewMode.mode}`, 20, y + 35);
    
    // Mode buttons
    const modes = ["hierarchy", "flat", "compact"];
    modes.forEach((mode, index) => {
        const buttonX = 20 + (index * 100);
        const isActive = mode === this.internalControls.viewMode.mode;
        
        ctx.fillStyle = isActive ? "#8a5cf6" : "#4a4a5a";
        ctx.fillRect(buttonX, y + 45, 90, 20);
        
        ctx.fillStyle = "#ffffff";
        ctx.fillText(mode, buttonX + 5, y + 58);
    });
};

UIControlPanelNode.prototype.drawFilterControl = function(ctx) {
    const y = this.internalControls.filter.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Filter", 20, y + 15);
    
    // Filter input background
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(20, y + 25, this.size[0] - 40, 25);
    ctx.strokeStyle = "#8a5cf6";
    ctx.strokeRect(20, y + 25, this.size[0] - 40, 25);
    
    // Filter text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    const filterText = this.internalControls.filter.text || "Type to filter nodes...";
    ctx.fillText(filterText, 25, y + 40);
};

UIControlPanelNode.prototype.drawZoomControl = function(ctx) {
    const y = this.internalControls.zoomControl.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Zoom Control", 20, y + 15);
    
    // Zoom level
    ctx.font = "10px Arial";
    ctx.fillText(`Level: ${(this.internalControls.zoomControl.level * 100).toFixed(0)}%`, 20, y + 35);
    
    // Zoom buttons
    ctx.fillStyle = "#4a4a5a";
    ctx.fillRect(20, y + 45, 40, 20);
    ctx.fillRect(70, y + 45, 40, 20);
    ctx.fillRect(120, y + 45, 60, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.fillText("−", 35, y + 58);
    ctx.fillText("+", 85, y + 58);
    ctx.fillText("Reset", 135, y + 58);
};

UIControlPanelNode.prototype.drawDisplayOptionsControl = function(ctx) {
    const y = this.internalControls.displayOptions.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Display Options", 20, y + 15);
    
    // Checkboxes
    const options = [
        { name: "Show Labels", value: this.internalControls.displayOptions.showLabels },
        { name: "Show Connections", value: this.internalControls.displayOptions.showConnections }
    ];
    
    options.forEach((option, index) => {
        const checkY = y + 35 + (index * 20);
        
        // Checkbox
        ctx.fillStyle = option.value ? "#10b981" : "#4a4a5a";
        ctx.fillRect(20, checkY - 8, 12, 12);
        
        // Checkmark
        if (option.value) {
            ctx.fillStyle = "#ffffff";
            ctx.font = "8px Arial";
            ctx.fillText("✓", 23, checkY);
        }
        
        // Label
        ctx.fillStyle = "#ffffff";
        ctx.font = "10px Arial";
        ctx.fillText(option.name, 40, checkY);
    });
};

UIControlPanelNode.prototype.drawNodeDetailsControl = function(ctx) {
    const y = this.internalControls.nodeDetails.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Node Details", 20, y + 15);
    
    // Selected node info
    ctx.font = "10px Arial";
    const selectedText = this.internalControls.nodeDetails.selectedNode 
        ? `Selected: ${this.internalControls.nodeDetails.selectedNode}`
        : "No node selected";
    ctx.fillText(selectedText, 20, y + 35);
};

UIControlPanelNode.prototype.drawStatusLegendControl = function(ctx) {
    const y = this.internalControls.statusLegend.y;
    
    // Background
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(10, y, this.size[0] - 20, 70);
    
    // Border
    ctx.strokeStyle = "#4a4a5a";
    ctx.lineWidth = 1;
    ctx.strokeRect(10, y, this.size[0] - 20, 70);
    
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Status Legend", 20, y + 15);
    
    // Legend items
    const statuses = [
        { name: "Running", color: "#10b981" },
        { name: "Idle", color: "#6b7280" },
        { name: "Error", color: "#ef4444" }
    ];
    
    statuses.forEach((status, index) => {
        const itemX = 20 + (index * 100);
        
        // Color indicator
        ctx.fillStyle = status.color;
        ctx.fillRect(itemX, y + 35, 10, 10);
        
        // Label
        ctx.fillStyle = "#ffffff";
        ctx.font = "8px Arial";
        ctx.fillText(status.name, itemX + 15, y + 43);
    });
};

UIControlPanelNode.prototype.wrapText = function(ctx, text, maxWidth, maxLines) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = '';
    
    for (let i = 0; i < words.length; i++) {
        const testLine = currentLine + (currentLine ? ' ' : '') + words[i];
        const metrics = ctx.measureText(testLine);
        
        if (metrics.width > maxWidth && currentLine) {
            lines.push(currentLine);
            currentLine = words[i];
            
            if (lines.length >= maxLines - 1) {
                // If we're at max lines, add ellipsis to the last line
                const remainingWords = words.slice(i);
                const lastLine = currentLine + (remainingWords.length > 1 ? '...' : '');
                lines.push(lastLine);
                break;
            }
        } else {
            currentLine = testLine;
        }
    }
    
    if (currentLine && lines.length < maxLines) {
        lines.push(currentLine);
    }
    
    return lines;
};

UIControlPanelNode.prototype.drawLayoutManagementControl = function(ctx) {
    const y = this.internalControls.layoutManagement.y;
    
    // Section header
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Layout Management", 20, y + 15);
    
    // Buttons
    const buttons = [
        { text: "Save Layout", x: 20, width: 80 },
        { text: "Load Layout", x: 110, width: 80 },
        { text: "Reset Layout", x: 200, width: 80 }
    ];
    
    buttons.forEach(button => {
        // Button background
        ctx.fillStyle = "#4a4a4a";
        ctx.fillRect(button.x, y + 25, button.width, 25);
        
        // Button border
        ctx.strokeStyle = "#666666";
        ctx.lineWidth = 1;
        ctx.strokeRect(button.x, y + 25, button.width, 25);
        
        // Button text
        ctx.fillStyle = "#ffffff";
        ctx.font = "10px Arial";
        const textWidth = ctx.measureText(button.text).width;
        const textX = button.x + (button.width - textWidth) / 2;
        ctx.fillText(button.text, textX, y + 40);
    });
};

UIControlPanelNode.prototype.onMouseDown = function(e, localpos, graphcanvas) {
    if (this.properties.collapsed) return false;
    
    // Handle clicks on internal controls
    const clickHandlers = [
        { control: 'websocket', handler: this.handleWebSocketClick },
        { control: 'taskInput', handler: this.handleTaskInputClick },
        { control: 'viewMode', handler: this.handleViewModeClick },
        { control: 'filter', handler: this.handleFilterClick },
        { control: 'zoomControl', handler: this.handleZoomClick },
        { control: 'displayOptions', handler: this.handleDisplayOptionsClick },
        { control: 'layoutManagement', handler: this.handleLayoutManagementClick }
    ];
    
    for (const { control, handler } of clickHandlers) {
        const controlY = this.internalControls[control].y;
        const controlHeight = control === 'taskInput' ? 110 : 70;
        
        if (localpos[1] >= controlY && localpos[1] <= controlY + controlHeight) {
            return handler.call(this, localpos, controlY);
        }
    }
    
    return false;
};

UIControlPanelNode.prototype.handleWebSocketClick = function(localpos, controlY) {
    // Toggle connection status
    this.internalControls.websocket.status = 
        this.internalControls.websocket.status === "connected" ? "disconnected" : "connected";
    this.setDirtyCanvas(true);
    return true;
};

UIControlPanelNode.prototype.handleTaskInputClick = function(localpos, controlY) {
    const relativeY = localpos[1] - controlY;
    
    // Check if clicking on start button
    if (relativeY >= 85 && relativeY <= 105 && localpos[0] >= 20 && localpos[0] <= 80) {
        this.internalControls.taskInput.status = "running";
        // Trigger start task
        if (window.CampfireValley && window.CampfireValley.startTask) {
            window.CampfireValley.startTask(this.internalControls.taskInput.text);
        }
        this.setDirtyCanvas(true);
        return true;
    }
    
    // Check if clicking on stop button
    if (relativeY >= 85 && relativeY <= 105 && localpos[0] >= 90 && localpos[0] <= 150) {
        this.internalControls.taskInput.status = "ready";
        // Trigger stop task
        if (window.CampfireValley && window.CampfireValley.stopTask) {
            window.CampfireValley.stopTask();
        }
        this.setDirtyCanvas(true);
        return true;
    }
    
    return false;
};

UIControlPanelNode.prototype.handleViewModeClick = function(localpos, controlY) {
    const relativeY = localpos[1] - controlY;
    
    // Check if clicking on mode buttons
    if (relativeY >= 45 && relativeY <= 65) {
        const modes = ["hierarchy", "flat", "compact"];
        const buttonIndex = Math.floor((localpos[0] - 20) / 100);
        
        if (buttonIndex >= 0 && buttonIndex < modes.length) {
            this.internalControls.viewMode.mode = modes[buttonIndex];
            this.setDirtyCanvas(true);
            return true;
        }
    }
    
    return false;
};

UIControlPanelNode.prototype.handleFilterClick = function(localpos, controlY) {
    // For now, just focus on the filter area
    // In a full implementation, this would open a text input
    return false;
};

UIControlPanelNode.prototype.handleZoomClick = function(localpos, controlY) {
    const relativeY = localpos[1] - controlY;
    
    // Check if clicking on zoom buttons
    if (relativeY >= 45 && relativeY <= 65) {
        if (localpos[0] >= 20 && localpos[0] <= 60) {
            // Zoom out
            this.internalControls.zoomControl.level = Math.max(0.1, this.internalControls.zoomControl.level - 0.1);
        } else if (localpos[0] >= 70 && localpos[0] <= 110) {
            // Zoom in
            this.internalControls.zoomControl.level = Math.min(3.0, this.internalControls.zoomControl.level + 0.1);
        } else if (localpos[0] >= 120 && localpos[0] <= 180) {
            // Reset zoom
            this.internalControls.zoomControl.level = 1.0;
        }
        this.setDirtyCanvas(true);
        return true;
    }
    
    return false;
};

UIControlPanelNode.prototype.handleDisplayOptionsClick = function(localpos, controlY) {
    const relativeY = localpos[1] - controlY;
    
    // Check if clicking on checkboxes
    if (relativeY >= 27 && relativeY <= 39 && localpos[0] >= 20 && localpos[0] <= 32) {
        // Show Labels checkbox
        this.internalControls.displayOptions.showLabels = !this.internalControls.displayOptions.showLabels;
        this.setDirtyCanvas(true);
        return true;
    }
    
    if (relativeY >= 47 && relativeY <= 59 && localpos[0] >= 20 && localpos[0] <= 32) {
        // Show Connections checkbox
        this.internalControls.displayOptions.showConnections = !this.internalControls.displayOptions.showConnections;
        this.setDirtyCanvas(true);
        return true;
    }
    
    return false;
};

UIControlPanelNode.prototype.handleLayoutManagementClick = function(localpos, controlY) {
    const y = controlY;
    const buttonY = y + 25;
    const buttonHeight = 25;
    
    // Check if click is within button area
    if (localpos[1] >= buttonY && localpos[1] <= buttonY + buttonHeight) {
        // Check which button was clicked
        if (localpos[0] >= 20 && localpos[0] <= 100) {
            // Save Layout button
            this.saveLayout();
        } else if (localpos[0] >= 110 && localpos[0] <= 190) {
            // Load Layout button
            this.loadLayout();
        } else if (localpos[0] >= 200 && localpos[0] <= 280) {
            // Reset Layout button
            this.resetLayout();
        }
    }
};

UIControlPanelNode.prototype.saveLayout = function() {
    if (this.graph) {
        const layoutData = {
            nodes: this.graph._nodes.map(node => ({
                id: node.id,
                type: node.type,
                pos: [node.pos[0], node.pos[1]],
                size: [node.size[0], node.size[1]],
                properties: node.properties
            }))
        };
        localStorage.setItem('campfire_layout', JSON.stringify(layoutData));
        console.log('Layout saved successfully');
    }
};

UIControlPanelNode.prototype.loadLayout = function() {
    const savedLayout = localStorage.getItem('campfire_layout');
    if (savedLayout && this.graph) {
        try {
            const layoutData = JSON.parse(savedLayout);
            this.graph.clear();
            
            layoutData.nodes.forEach(nodeData => {
                const node = LiteGraph.createNode(nodeData.type);
                if (node) {
                    node.pos = nodeData.pos;
                    node.size = nodeData.size;
                    if (nodeData.properties) {
                        Object.assign(node.properties, nodeData.properties);
                    }
                    this.graph.add(node);
                }
            });
            console.log('Layout loaded successfully');
        } catch (e) {
            console.error('Failed to load layout:', e);
        }
    }
};

UIControlPanelNode.prototype.resetLayout = function() {
    if (this.graph) {
        this.graph.clear();
        console.log('Layout reset successfully');
    }
};

// Register all nodes with LiteGraph
LiteGraph.registerNodeType("campfire/ui_control_panel", UIControlPanelNode);
LiteGraph.registerNodeType("campfire/task_input", TaskInputNode);
LiteGraph.registerNodeType("campfire/view_mode", ViewModeNode);
LiteGraph.registerNodeType("campfire/filter", FilterNode);
LiteGraph.registerNodeType("campfire/zoom_control", ZoomControlNode);
LiteGraph.registerNodeType("campfire/display_options", DisplayOptionsNode);
LiteGraph.registerNodeType("campfire/node_details", NodeDetailsNode);
LiteGraph.registerNodeType("campfire/status_legend", StatusLegendNode);
LiteGraph.registerNodeType("campfire/valley", ValleyNode);
LiteGraph.registerNodeType("campfire/dock", DockNode);
LiteGraph.registerNodeType("campfire/dockmaster_campfire", DockmasterCampfireNode);
LiteGraph.registerNodeType("campfire/sanitizer_campfire", SanitizerCampfireNode);
LiteGraph.registerNodeType("campfire/justice_campfire", JusticeCampfireNode);
LiteGraph.registerNodeType("campfire/campfire", CampfireNode);
LiteGraph.registerNodeType("campfire/loader_camper", LoaderCamperNode);
LiteGraph.registerNodeType("campfire/router_camper", RouterCamperNode);
LiteGraph.registerNodeType("campfire/packer_camper", PackerCamperNode);
LiteGraph.registerNodeType("campfire/scanner_camper", ScannerCamperNode);
LiteGraph.registerNodeType("campfire/filter_camper", FilterCamperNode);
LiteGraph.registerNodeType("campfire/quarantine_camper", QuarantineCamperNode);
LiteGraph.registerNodeType("campfire/detector_camper", DetectorCamperNode);
LiteGraph.registerNodeType("campfire/enforcer_camper", EnforcerCamperNode);
LiteGraph.registerNodeType("campfire/governor_camper", GovernorCamperNode);
LiteGraph.registerNodeType("campfire/camper", CamperNode);
LiteGraph.registerNodeType("campfire/websocket_data", WebSocketDataNode);

// ===== HEXAGONAL VALLEY NODE =====

function HexagonalValleyNode() {
    // Call ValleyNode constructor to inherit all its functionality
    ValleyNode.call(this);
    
    // Override visual properties for hexagonal display
    this.title = "Hexagonal Valley";
    this.size = [480, 416]; // 4x larger hexagon dimensions (doubled again)
    
    // Add hexagon-specific properties
    this.properties.valley_type = "mountain"; // mountain, forest, plains, water, desert
    
    // Define hexagon geometry - 4x larger
    this.hexRadius = 200; // 4x original size (was 50, then 100, now 200)
    this.hexHeight = this.hexRadius * Math.sqrt(3);
    this.hexWidth = this.hexRadius * 2;
    
    // Add standard inputs for compatibility with other nodes
    this.addInput("dock_connection", "dock");
    this.addInput("campfire_connection", "campfire");
    
    // Add multiple directional input/output slots for better connectivity
    this.addInput("North", "valley_connection");
    this.addInput("Northeast", "valley_connection");
    this.addInput("Southeast", "valley_connection");
    this.addOutput("South", "valley_connection");
    this.addOutput("Southwest", "valley_connection");
    this.addOutput("Northwest", "valley_connection");
    
    // Enable proper LiteGraph functionality
    this.shape = LiteGraph.BOX_SHAPE; // Use box shape for proper connection handling
    this.resizable = false; // Fixed size hexagon
    this.horizontal = false;
    this.movable = true; // Explicitly enable dragging
    this.removable = true;
    this.clonable = true;
    
    // Selection and interaction state
    this.selected = false;
    this.is_selected = false;
    this.mouseOver = false;
    
    // Override default node behavior for hexagonal shape
    this.flags = this.flags || {};
    this.flags.collapsed = false; // Never collapse hexagonal nodes
    this.flags.no_panel = true; // Skip default rectangular panel/title rendering
}

HexagonalValleyNode.title = "Hexagonal Valley";
HexagonalValleyNode.desc = "A hexagonal valley node representing a territory in the CampfireValley system";

// Apply dynamic sizing mixin to Hexagonal Valley node
Object.assign(HexagonalValleyNode.prototype, DynamicSizingMixin);

// Override the default drawing to completely replace rectangular widget
HexagonalValleyNode.prototype.onDrawBackground = function(ctx) {
    // COMPLETELY override default drawing - don't call parent method
    // This prevents the rectangular widget from drawing behind our hexagon
    
    if (this.flags.collapsed) return;
    
    // Clear the entire node area first to prevent any default drawing
    ctx.clearRect(0, 0, this.size[0], this.size[1]);
    
    const centerX = this.size[0] / 2;
    const centerY = this.size[1] / 2;
    const radius = Math.min(this.size[0], this.size[1]) * 0.4; // Adjusted for larger size
    
    // Draw outer glow for selection or hover
    if (this.selected || this.flags.selected || this.mouseOver) {
        const glowRadius = radius + 8;
        const gradient = ctx.createRadialGradient(centerX, centerY, radius, centerX, centerY, glowRadius);
        
        if (this.selected || this.flags.selected) {
            gradient.addColorStop(0, "rgba(255, 255, 255, 0.3)");
            gradient.addColorStop(1, "rgba(255, 255, 255, 0)");
        } else if (this.mouseOver) {
            gradient.addColorStop(0, "rgba(100, 200, 255, 0.2)");
            gradient.addColorStop(1, "rgba(100, 200, 255, 0)");
        }
        
        ctx.fillStyle = gradient;
        this.drawHexagon(ctx, centerX, centerY, glowRadius, gradient);
    }
    
    // Draw hexagon background
    this.drawHexagon(ctx, centerX, centerY, radius, this.getValleyColor());
    
    // Draw selection highlighting with bright border if selected
    if (this.selected || this.flags.selected) {
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 6;
        ctx.shadowColor = "#FFFFFF";
        ctx.shadowBlur = 10;
        this.drawHexagonStroke(ctx, centerX, centerY, radius + 3);
        ctx.shadowBlur = 0; // Reset shadow
    }
    
    // Draw hexagon border
    ctx.strokeStyle = this.getValleyBorderColor();
    ctx.lineWidth = 3;
    this.drawHexagonStroke(ctx, centerX, centerY, radius);
};

// Override the default node rendering completely
HexagonalValleyNode.prototype.onDrawNode = function(ctx, graphcanvas) {
    // Completely override default node drawing to prevent rectangular widget
    // This is the main drawing method that LiteGraph calls
    
    // Call our custom background drawing
    this.onDrawBackground(ctx);
    
    // Call our custom foreground drawing
    this.onDrawForeground(ctx);
    
    // Draw connection slots manually since we're overriding default drawing
    this.drawConnectionSlots(ctx, graphcanvas);
    
    // Don't call the parent onDrawNode method to prevent rectangular drawing
};

// Custom connection slot rendering for hexagonal nodes
HexagonalValleyNode.prototype.drawConnectionSlots = function(ctx, graphcanvas) {
    const centerX = this.size[0] / 2;
    const centerY = this.size[1] / 2;
    const radius = Math.min(this.size[0], this.size[1]) * 0.4;
    
    // Draw input slots
    if (this.inputs) {
        for (let i = 0; i < this.inputs.length; i++) {
            const input = this.inputs[i];
            const pos = this.getConnectionPos(true, i);
            
            // Draw input slot circle
            ctx.fillStyle = input.link ? "#4CAF50" : "#2196F3"; // Green if connected, blue if not
            ctx.beginPath();
            ctx.arc(pos[0], pos[1], 6, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw slot border
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    }
    
    // Draw output slots
    if (this.outputs) {
        for (let i = 0; i < this.outputs.length; i++) {
            const output = this.outputs[i];
            const pos = this.getConnectionPos(false, i);
            
            // Draw output slot circle
            ctx.fillStyle = output.links && output.links.length > 0 ? "#FF9800" : "#2196F3"; // Orange if connected, blue if not
            ctx.beginPath();
            ctx.arc(pos[0], pos[1], 6, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw slot border
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    }
};

HexagonalValleyNode.prototype.onDrawForeground = function(ctx) {
    if (this.flags.collapsed) return;
    
    const centerX = this.size[0] / 2;
    const centerY = this.size[1] / 2;
    const radius = Math.min(this.size[0], this.size[1]) * 0.4; // Adjusted for larger size
    
    // Draw valley type icon (much larger)
    this.drawValleyIcon(ctx, centerX, centerY - 40, radius * 0.5);
    
    // Draw valley name (much larger font)
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 32px Arial";
    ctx.textAlign = "center";
    ctx.fillText(this.properties.valley_name, centerX, centerY + 20);
    
    // Draw valley type
    ctx.font = "24px Arial";
    ctx.fillText(this.properties.valley_type.charAt(0).toUpperCase() + this.properties.valley_type.slice(1), centerX, centerY + 50);
    
    // Draw prosperity and status info
    ctx.font = "20px Arial";
    ctx.fillText(`Prosperity: ${this.properties.prosperity}%`, centerX, centerY + 80);
    ctx.fillText(`Status: ${this.properties.status}`, centerX, centerY + 104);
    
    // Draw campfire and camper counts if available
    if (this.properties.total_campfires > 0 || this.properties.total_campers > 0) {
        ctx.font = "18px Arial";
        ctx.fillText(`🔥 ${this.properties.total_campfires} | 👥 ${this.properties.total_campers}`, centerX, centerY + 128);
    }
    
    // Draw status indicators around the hexagon
    this.drawStatusIndicators(ctx, centerX, centerY, radius);
    
    // Draw connection points at hexagon vertices (blue circles like in user's image)
    this.drawConnectionPoints(ctx, centerX, centerY, radius);
};

HexagonalValleyNode.prototype.drawHexagon = function(ctx, centerX, centerY, radius, fillColor) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i;
        const x = centerX + radius * Math.cos(angle);
        const y = centerY + radius * Math.sin(angle);
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
};

HexagonalValleyNode.prototype.drawHexagonStroke = function(ctx, centerX, centerY, radius) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i;
        const x = centerX + radius * Math.cos(angle);
        const y = centerY + radius * Math.sin(angle);
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.closePath();
    ctx.stroke();
};

HexagonalValleyNode.prototype.drawValleyIcon = function(ctx, centerX, centerY, iconRadius) {
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    
    switch (this.properties.valley_type) {
        case "mountain":
            this.drawMountainIcon(ctx, centerX, centerY, iconRadius);
            break;
        case "forest":
            this.drawForestIcon(ctx, centerX, centerY, iconRadius);
            break;
        case "plains":
            this.drawPlainsIcon(ctx, centerX, centerY, iconRadius);
            break;
        case "water":
            this.drawWaterIcon(ctx, centerX, centerY, iconRadius);
            break;
        case "desert":
            this.drawDesertIcon(ctx, centerX, centerY, iconRadius);
            break;
        default:
            this.drawMountainIcon(ctx, centerX, centerY, iconRadius);
    }
};

HexagonalValleyNode.prototype.drawMountainIcon = function(ctx, centerX, centerY, radius) {
    // Draw mountain peaks
    ctx.beginPath();
    ctx.moveTo(centerX - radius * 0.8, centerY + radius * 0.3);
    ctx.lineTo(centerX - radius * 0.3, centerY - radius * 0.5);
    ctx.lineTo(centerX, centerY - radius * 0.2);
    ctx.lineTo(centerX + radius * 0.3, centerY - radius * 0.7);
    ctx.lineTo(centerX + radius * 0.8, centerY + radius * 0.3);
    ctx.closePath();
    ctx.fill();
    
    // Add snow caps
    ctx.fillStyle = "#e0e0e0";
    ctx.beginPath();
    ctx.moveTo(centerX - radius * 0.3, centerY - radius * 0.5);
    ctx.lineTo(centerX - radius * 0.1, centerY - radius * 0.3);
    ctx.lineTo(centerX + radius * 0.1, centerY - radius * 0.4);
    ctx.lineTo(centerX, centerY - radius * 0.2);
    ctx.closePath();
    ctx.fill();
    
    ctx.beginPath();
    ctx.moveTo(centerX + radius * 0.3, centerY - radius * 0.7);
    ctx.lineTo(centerX + radius * 0.5, centerY - radius * 0.4);
    ctx.lineTo(centerX + radius * 0.1, centerY - radius * 0.4);
    ctx.closePath();
    ctx.fill();
};

HexagonalValleyNode.prototype.drawForestIcon = function(ctx, centerX, centerY, radius) {
    // Draw trees
    for (let i = 0; i < 3; i++) {
        const offsetX = (i - 1) * radius * 0.4;
        const offsetY = (i % 2) * radius * 0.2;
        
        // Tree trunk
        ctx.fillStyle = "#8B4513";
        ctx.fillRect(centerX + offsetX - 2, centerY + offsetY + radius * 0.2, 4, radius * 0.3);
        
        // Tree foliage
        ctx.fillStyle = "#228B22";
        ctx.beginPath();
        ctx.arc(centerX + offsetX, centerY + offsetY, radius * 0.25, 0, Math.PI * 2);
        ctx.fill();
    }
};

HexagonalValleyNode.prototype.drawPlainsIcon = function(ctx, centerX, centerY, radius) {
    // Draw grass/wheat
    ctx.strokeStyle = "#90EE90";
    ctx.lineWidth = 2;
    
    for (let i = 0; i < 8; i++) {
        const angle = (Math.PI * 2 / 8) * i;
        const startX = centerX + Math.cos(angle) * radius * 0.3;
        const startY = centerY + Math.sin(angle) * radius * 0.3;
        const endX = centerX + Math.cos(angle) * radius * 0.6;
        const endY = centerY + Math.sin(angle) * radius * 0.6;
        
        ctx.beginPath();
        ctx.moveTo(startX, startY);
        ctx.lineTo(endX, endY);
        ctx.stroke();
    }
};

HexagonalValleyNode.prototype.drawWaterIcon = function(ctx, centerX, centerY, radius) {
    // Draw water waves
    ctx.strokeStyle = "#4169E1";
    ctx.lineWidth = 2;
    
    for (let i = 0; i < 3; i++) {
        const y = centerY - radius * 0.3 + i * radius * 0.3;
        ctx.beginPath();
        ctx.moveTo(centerX - radius * 0.5, y);
        
        for (let x = -radius * 0.5; x <= radius * 0.5; x += radius * 0.2) {
            const waveY = y + Math.sin((x / radius) * Math.PI * 2) * radius * 0.1;
            ctx.lineTo(centerX + x, waveY);
        }
        ctx.stroke();
    }
};

HexagonalValleyNode.prototype.drawDesertIcon = function(ctx, centerX, centerY, radius) {
    // Draw sand dunes
    ctx.fillStyle = "#F4A460";
    
    // Large dune
    ctx.beginPath();
    ctx.arc(centerX - radius * 0.2, centerY + radius * 0.1, radius * 0.4, Math.PI, 0);
    ctx.fill();
    
    // Small dune
    ctx.beginPath();
    ctx.arc(centerX + radius * 0.3, centerY + radius * 0.2, radius * 0.25, Math.PI, 0);
    ctx.fill();
    
    // Cactus
    ctx.fillStyle = "#228B22";
    ctx.fillRect(centerX + radius * 0.1, centerY - radius * 0.3, 4, radius * 0.5);
    ctx.fillRect(centerX + radius * 0.1 - 8, centerY - radius * 0.1, 12, 4);
};

HexagonalValleyNode.prototype.drawStatusIndicators = function(ctx, centerX, centerY, radius) {
    // Draw small status dots around the hexagon
    const indicators = [
        { label: "P", value: this.properties.population || 0, color: "#4CAF50", angle: 0 },
        { label: "R", value: this.properties.resources || 0, color: "#FF9800", angle: Math.PI / 3 },
        { label: "C", value: this.properties.connections || 0, color: "#2196F3", angle: 2 * Math.PI / 3 }
    ];
    
    indicators.forEach(indicator => {
        const dotX = centerX + Math.cos(indicator.angle) * (radius + 15);
        const dotY = centerY + Math.sin(indicator.angle) * (radius + 15);
        
        // Draw indicator dot
        ctx.fillStyle = indicator.color;
        ctx.beginPath();
        ctx.arc(dotX, dotY, 6, 0, Math.PI * 2);
        ctx.fill();
        
        // Draw indicator value
        ctx.fillStyle = "#ffffff";
        ctx.font = "8px Arial";
        ctx.textAlign = "center";
        ctx.fillText((indicator.value || 0).toString(), dotX, dotY + 2);
    });
};

HexagonalValleyNode.prototype.drawConnectionPoints = function(ctx, centerX, centerY, radius) {
    // Draw blue connection points at hexagon vertices
    for (let i = 0; i < 6; i++) {
        const angle = (i * Math.PI) / 3 - Math.PI / 2; // Start from top vertex
        const pointX = centerX + Math.cos(angle) * radius;
        const pointY = centerY + Math.sin(angle) * radius;
        
        // Draw blue connection point
        ctx.fillStyle = "#2196F3";
        ctx.beginPath();
        ctx.arc(pointX, pointY, 4, 0, Math.PI * 2);
        ctx.fill();
        
        // Add white border for visibility
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1;
        ctx.stroke();
    }
};

HexagonalValleyNode.prototype.getValleyColor = function() {
    // Uniform color by node type: valley = green
    return "#2ECC71";
};

HexagonalValleyNode.prototype.getValleyBorderColor = function() {
    return this.properties.status === "active" ? "#FFD700" : 
           this.properties.status === "inactive" ? "#808080" : "#FF4444";
};

HexagonalValleyNode.prototype.onExecute = function() {
    // Count active connections
    let activeConnections = 0;
    if (this.inputs) {
        for (let i = 0; i < this.inputs.length; i++) {
            if (this.inputs[i].link) activeConnections++;
        }
    }
    this.properties.connections = activeConnections;
    
    // Simulate population and resource changes
    if (this.properties.status === "active") {
        this.properties.population = Math.min(99, this.properties.population + Math.random() * 0.1);
        this.properties.resources = Math.min(99, this.properties.resources + Math.random() * 0.05);
        
        // Update prosperity based on connections and activity
        this.properties.prosperity = Math.min(100, Math.max(0, 
            this.properties.prosperity + (activeConnections * 0.5) - 0.1 + Math.random() * 0.2
        ));
    }
    
    // Create valley data object
    const valleyData = {
        name: this.properties.valley_name,
        type: this.properties.valley_type,
        status: this.properties.status,
        population: this.properties.population,
        resources: this.properties.resources,
        connections: this.properties.connections,
        prosperity: this.properties.prosperity,
        growth_stage: this.properties.growth_stage,
        total_campfires: this.properties.total_campfires,
        total_campers: this.properties.total_campers
    };
    
    // Output data through all connection points
    for (let i = 0; i < this.outputs.length; i++) {
        this.setOutputData(i, valleyData);
    }
};

HexagonalValleyNode.prototype.onPropertyChanged = function(name, value) {
    if (name === "valley_type") {
        this.setDirtyCanvas(true, true);
    }
};

// Override connection positioning to place slots at hexagon vertices
HexagonalValleyNode.prototype.getConnectionPos = function(is_input, slot_number, out) {
    out = out || [0, 0];
    
    const centerX = this.size[0] / 2;
    const centerY = this.size[1] / 2;
    const radius = Math.min(this.size[0], this.size[1]) * 0.4;
    
    // Define hexagon vertex positions (starting from top, going clockwise)
    const vertices = [
        { angle: -Math.PI / 2, name: "North" },      // Top
        { angle: -Math.PI / 6, name: "Northeast" },  // Top-right
        { angle: Math.PI / 6, name: "Southeast" },   // Bottom-right
        { angle: Math.PI / 2, name: "South" },       // Bottom
        { angle: 5 * Math.PI / 6, name: "Southwest" }, // Bottom-left
        { angle: -5 * Math.PI / 6, name: "Northwest" } // Top-left
    ];
    
    // Map slot numbers to vertex positions
    let vertexIndex = slot_number;
    
    // Handle dock_connection and campfire_connection outputs
    if (!is_input && slot_number >= 3) {
        if (slot_number === 6) { // dock_connection
            vertexIndex = 3; // South vertex
        } else if (slot_number === 7) { // campfire_connection
            vertexIndex = 0; // North vertex
        }
    }
    
    // Ensure we have a valid vertex
    if (vertexIndex >= 0 && vertexIndex < vertices.length) {
        const vertex = vertices[vertexIndex];
        out[0] = this.pos[0] + centerX + radius * Math.cos(vertex.angle);
        out[1] = this.pos[1] + centerY + radius * Math.sin(vertex.angle);
    } else {
        // Fallback to center if invalid slot
        out[0] = this.pos[0] + centerX;
        out[1] = this.pos[1] + centerY;
    }
    
    return out;
};

// Enhanced collision detection for hexagonal shape
HexagonalValleyNode.prototype.isPointInside = function(x, y) {
    const centerX = this.size[0] / 2;
    const centerY = this.size[1] / 2;
    const radius = Math.min(this.size[0], this.size[1]) * 0.4;
    
    // Proper hexagon collision detection
    const dx = Math.abs(x - centerX);
    const dy = Math.abs(y - centerY);
    
    // Check if point is within hexagon bounds
    if (dx > radius * 0.866 || dy > radius) return false;
    if (dx <= radius * 0.5) return true;
    
    // Check diagonal edges
    const slope = Math.sqrt(3);
    return (dy <= radius - slope * (dx - radius * 0.5));
};

// Enhanced mouse events for selection and interaction
HexagonalValleyNode.prototype.onMouseDown = function(e, localpos, graphcanvas) {
    if (e.which === 1) { // Left click
        this.selected = true;
        this.is_selected = true;
        if (graphcanvas) {
            graphcanvas.selectNode(this);
        }
        this.setDirtyCanvas(true, true);
        return true;
    }
    return false;
};

HexagonalValleyNode.prototype.onMouseUp = function(e, localpos, graphcanvas) {
    // Handle any mouse up logic here
    return false;
};

HexagonalValleyNode.prototype.onMouseMove = function(e, localpos, graphcanvas) {
    // Handle hover state
    const wasMouseOver = this.mouseOver;
    this.mouseOver = this.isPointInside(localpos[0], localpos[1]);
    
    if (wasMouseOver !== this.mouseOver) {
        this.setDirtyCanvas(true, true);
    }
    
    return false;
};

HexagonalValleyNode.prototype.onMouseEnter = function(e, localpos, graphcanvas) {
    this.mouseOver = true;
    this.setDirtyCanvas(true, true);
};

HexagonalValleyNode.prototype.onMouseLeave = function(e, localpos, graphcanvas) {
    this.mouseOver = false;
    this.setDirtyCanvas(true, true);
};

// Enhanced selection state changes
HexagonalValleyNode.prototype.onSelected = function() {
    this.is_selected = true;
    this.selected = true;
    this.setDirtyCanvas(true, true);
};

HexagonalValleyNode.prototype.onDeselected = function() {
    this.is_selected = false;
    this.selected = false;
    this.setDirtyCanvas(true, true);
};

// Override getBounding to return proper hexagon bounds
HexagonalValleyNode.prototype.getBounding = function(out) {
    out = out || new Float32Array(4);
    const radius = Math.min(this.size[0], this.size[1]) * 0.4;
    const centerX = this.pos[0] + this.size[0] / 2;
    const centerY = this.pos[1] + this.size[1] / 2;
    
    out[0] = centerX - radius; // left
    out[1] = centerY - radius; // top
    out[2] = radius * 2; // width
    out[3] = radius * 2; // height
    
    return out;
};

// Register the hexagonal valley node
LiteGraph.registerNodeType("campfire/hexagonal_valley", HexagonalValleyNode);

// === Hex Overrides for Original Nodes (inheritance without duplication) ===
// Generic hex mixin to replace rectangular rendering and connector geometry
const HexNodeBaseMixin = {
    onDrawBackground: function(ctx) {
        if (this.flags && this.flags.collapsed) return;
        const centerX = this.size[0] / 2;
        const centerY = this.size[1] / 2;
        const radius = Math.min(this.size[0], this.size[1]) * 0.4;

        // layout metrics for top-aligned header (icon + title)
        const paddingTop = Math.max(6, Math.round(radius * 0.10)); // tighter header
        const iconSizeTop = Math.round(radius * 0.8);
        const iconYTop = Math.round(centerY - radius + paddingTop);
        const titleGap = Math.round(radius * 0.08); // reduced gap
        const titleFontSize = Math.max(10, Math.round(radius * 0.18)); // ~50% smaller
        const propFontSize = Math.max(9, Math.round(radius * 0.13));  // ~50% smaller
        const titleY = iconYTop + iconSizeTop + titleGap;
        // top header contrast band to reduce background pattern
        (function() {
            const headerHeight = Math.round(iconSizeTop + titleGap + titleFontSize + Math.max(2, Math.round(titleFontSize * 0.2)));
            ctx.save();
            // clip to hex
            ctx.beginPath();
            for (let i = 0; i < 6; i++) {
                const angle = (Math.PI / 3) * i;
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.clip();
            ctx.fillStyle = "rgba(0, 0, 0, 0.20)";
            ctx.fillRect(centerX - radius, Math.round(centerY - radius), radius * 2, headerHeight);
            ctx.restore();
        })();

        // subtle glow on hover/selection
        const isSelected = this.is_selected || this.selected || (this.flags && this.flags.selected);
        if (isSelected || this.mouseOver) {
            const glowRadius = radius + 8;
            const gradient = ctx.createRadialGradient(centerX, centerY, radius, centerX, centerY, glowRadius);
            gradient.addColorStop(0, "rgba(255,255,255,0.25)");
            gradient.addColorStop(1, "rgba(255,255,255,0)");
            ctx.fillStyle = gradient;
            this.drawHexagon(ctx, centerX, centerY, glowRadius, gradient);
        }

        // base fill
        this.drawHexagon(ctx, centerX, centerY, radius, this.getHexFillColor());

        // scenic SVG overlay clipped to hex
        if (!this._hexBg) {
            const img = new Image();
            img.src = "/static/img/hex_bg.svg";
            img.onload = () => { this._hexBg_loaded = true; this.setDirtyCanvas(true, true); };
            img.onerror = () => { this._hexBg_error = true; };
            this._hexBg = img;
        }
        if (this._hexBg && (this._hexBg_loaded || this._hexBg.complete) && !this._hexBg_error) {
            ctx.save();
            // clip to hex path
            ctx.beginPath();
            for (let i = 0; i < 6; i++) {
                const angle = (Math.PI / 3) * i;
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.clip();
            const prevAlpha = ctx.globalAlpha;
            ctx.globalAlpha = 0.55;
            ctx.drawImage(this._hexBg, centerX - radius, centerY - radius, radius * 2, radius * 2);
            ctx.globalAlpha = prevAlpha;
            ctx.restore();
        }

        // border stroke on top
        ctx.strokeStyle = this.getHexBorderColor();
        ctx.lineWidth = 3;
        this.drawHexagonStroke(ctx, centerX, centerY, radius);
    },

    onDrawForeground: function(ctx) {
        if (this.flags && this.flags.collapsed) return;
        const centerX = this.size[0] / 2;
        const centerY = this.size[1] / 2;
        const radius = Math.min(this.size[0], this.size[1]) * 0.4;

        // layout metrics for top-aligned header (icon + title)
        const paddingTop = Math.max(4, Math.round(radius * 0.06)); // push icon closer to top
        const iconSizeTop = Math.round(radius * 0.72); // slightly smaller icon
        const iconYTop = Math.round(centerY - radius + paddingTop);
        const titleGap = Math.round(radius * 0.06); // tighter gap
        const titleFontSize = Math.max(10, Math.round(radius * 0.14)); // smaller title
        const propFontSize = Math.max(9, Math.round(radius * 0.11));  // smaller details
        const titleY = iconYTop + iconSizeTop + titleGap;

        // draw foreground icon
        const typeStr = (this.type || "").toLowerCase();
        let iconPath = null;
        const isCamper = (typeStr.includes("/camper") || /_camper$/.test(typeStr));
        if (typeStr.includes("/valley")) iconPath = "/static/img/valley_icon.svg";
        else if (typeStr.includes("/dock")) iconPath = "/static/img/dock_icon.svg";
        else if (typeStr.includes("/campfire") || /_campfire$/.test(typeStr)) iconPath = "/static/img/campfire_icon.svg";

        if (isCamper) {
            const iconSize = iconSizeTop;
            const iconY = iconYTop;
            const headR = iconSize * 0.15;
            const cx = centerX;
            const headCY = iconY + headR + 6;
            const bodyLen = iconSize * 0.45;
            const shoulderY = headCY + headR + 6;
            const hipY = shoulderY + bodyLen * 0.5;
            const footY = shoulderY + bodyLen;

            ctx.save();
            // clip to hex
            ctx.beginPath();
            for (let i = 0; i < 6; i++) {
                const angle = (Math.PI / 3) * i;
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.clip();

            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 3;
            ctx.lineCap = "round";

            // head
            ctx.beginPath();
            ctx.arc(cx, headCY, headR, 0, Math.PI * 2);
            ctx.stroke();

            // body
            ctx.beginPath();
            ctx.moveTo(cx, shoulderY);
            ctx.lineTo(cx, hipY);
            ctx.stroke();

            // arms
            const armLen = iconSize * 0.28;
            ctx.beginPath();
            ctx.moveTo(cx, shoulderY);
            ctx.lineTo(cx - armLen, shoulderY + armLen * 0.2);
            ctx.moveTo(cx, shoulderY);
            ctx.lineTo(cx + armLen, shoulderY + armLen * 0.2);
            ctx.stroke();

            // legs
            const legLen = iconSize * 0.35;
            ctx.beginPath();
            ctx.moveTo(cx, hipY);
            ctx.lineTo(cx - legLen * 0.5, footY);
            ctx.moveTo(cx, hipY);
            ctx.lineTo(cx + legLen * 0.5, footY);
            ctx.stroke();

            ctx.restore();
        } else if (iconPath) {
            if (!this._hexIcon || this._hexIcon_path !== iconPath) {
                const img = new Image();
                img.crossOrigin = "anonymous";
                img.onload = () => { this._hexIcon_loaded = true; this.setDirtyCanvas(true, true); };
                img.onerror = () => { this._hexIcon_error = true; };
                img.src = iconPath;
                this._hexIcon = img;
                this._hexIcon_path = iconPath;
                this._hexIcon_error = false;
                this._hexIcon_loaded = false;
            }
            if (this._hexIcon && (this._hexIcon_loaded || this._hexIcon.complete) && !this._hexIcon_error) {
                const iconSize = iconSizeTop;
                const iconY = iconYTop;
                ctx.save();
                ctx.beginPath();
                for (let i = 0; i < 6; i++) {
                    const angle = (Math.PI / 3) * i;
                    const x = centerX + radius * Math.cos(angle);
                    const y = centerY + radius * Math.sin(angle);
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                }
                ctx.closePath();
                ctx.clip();
                ctx.drawImage(this._hexIcon, centerX - iconSize / 2, iconY, iconSize, iconSize);
                ctx.restore();
            } else if (this._hexIcon_error) {
                // emoji fallback
                ctx.fillStyle = "#ffffff";
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                ctx.font = Math.round(radius * 0.6) + "px Arial";
                const emoji = typeStr.includes("/campfire") ? "🔥" : (typeStr.includes("/dock") ? "⚓" : "🏞️");
                ctx.fillText(emoji, centerX, iconYTop + Math.round(iconSizeTop * 0.15));
            }
        }

        // title: show specific camper role when available
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.font = "bold " + titleFontSize + "px Arial";
        let displayTitle = this.title || (this.type || "Node").split('/').pop().toUpperCase();
        const tstr = (this.type || "").toLowerCase();
        const isCamperTitle = (tstr.includes("/camper") || /_camper$/.test(tstr));
        if (isCamperTitle) {
            const match = tstr.match(/\/([a-z0-9]+)_camper$/);
            const roleGuess = match && match[1] ? match[1].toUpperCase() : null;
            const roleProp = (this.properties && (this.properties.role || this.properties.camper_role || this.properties.kind)) || null;
            if (roleProp || roleGuess) {
                displayTitle = String(roleProp || roleGuess).toUpperCase();
            }
        }
        ctx.fillText(displayTitle, centerX, titleY);

        // show up to 3 key properties
        const keys = Object.keys(this.properties || {});
        ctx.font = propFontSize + "px Arial";
        for (let i = 0; i < Math.min(3, keys.length); i++) {
            const k = keys[i];
            const v = this.properties[k];
            const y = titleY + titleFontSize + 8 + i * (propFontSize + 6);
            ctx.fillText(`${k}: ${v}`, centerX, y);
        }

        // draw connection points
        this.drawConnectionPoints(ctx, centerX, centerY, radius);
    },

    onDrawNode: function(ctx, graphcanvas) {
        if (this.flags && this.flags.collapsed) return;
        this.onDrawBackground(ctx);
        this.onDrawForeground(ctx);
        this.drawConnectionSlots(ctx, graphcanvas);
    },

    drawConnectionSlots: function(ctx, graphcanvas) {
        if (this.inputs) {
            for (let i = 0; i < this.inputs.length; i++) {
                const pos = this.getConnectionPos(true, i);
                ctx.fillStyle = this.inputs[i].link ? "#4CAF50" : "#2196F3";
                ctx.beginPath(); ctx.arc(pos[0], pos[1], 6, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2; ctx.stroke();
            }
        }
        if (this.outputs) {
            for (let i = 0; i < this.outputs.length; i++) {
                const pos = this.getConnectionPos(false, i);
                const connected = this.outputs[i].links && this.outputs[i].links.length > 0;
                ctx.fillStyle = connected ? "#FF9800" : "#2196F3";
                ctx.beginPath(); ctx.arc(pos[0], pos[1], 6, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2; ctx.stroke();
            }
        }
    },

    drawHexagon: HexagonalValleyNode.prototype.drawHexagon,
    drawHexagonStroke: HexagonalValleyNode.prototype.drawHexagonStroke,

    drawConnectionPoints: function(ctx, centerX, centerY, radius) {
        const points = [];
        for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i;
            points.push([centerX + radius * Math.cos(angle), centerY + radius * Math.sin(angle)]);
        }
        ctx.fillStyle = "#1e3a8a";
        for (const p of points) { ctx.beginPath(); ctx.arc(p[0], p[1], 5, 0, Math.PI * 2); ctx.fill(); }
    },

    getHexFillColor: function() {
        const t = this.type || "";
        if (t.startsWith("campfire/valley")) return "#2ECC71";
        if (t.startsWith("campfire/dock")) return "#1E90FF";
        if (t === "campfire/campfire" || /_campfire$/.test(t)) return "#FF9800";
        if (t === "campfire/camper" || /_camper$/.test(t)) return "#FFD700";
        const status = (this.properties && this.properties.status) || "idle";
        switch (status) {
            case "active": return "#3a6ea1";
            case "warning": return "#a13e3a";
            case "error": return "#7a1b1b";
            default: return "#315a85";
        }
    },
    getHexBorderColor: function() { return "#ffffff"; },

    getConnectionPos: function(is_input, slot_number, out) {
        out = out || [0, 0];
        const w = this.size[0], h = this.size[1];
        const centerX = w / 2, centerY = h / 2;
        const radius = Math.min(w, h) * 0.4;
        const anglesInput = [Math.PI, (2 * Math.PI) / 3, (4 * Math.PI) / 3];
        const anglesOutput = [0, (5 * Math.PI) / 3, Math.PI / 3];
        const angles = is_input ? anglesInput : anglesOutput;
        const angle = angles[slot_number % angles.length];
        out[0] = this.pos[0] + centerX + radius * Math.cos(angle);
        out[1] = this.pos[1] + centerY + radius * Math.sin(angle);
        return out;
    },

    isPointInside: function(x, y) {
        const localX = x - this.pos[0];
        const localY = y - this.pos[1];
        const centerX = this.size[0] / 2, centerY = this.size[1] / 2;
        const radius = Math.min(this.size[0], this.size[1]) * 0.4;
        const dx = localX - centerX, dy = localY - centerY;
        return (dx * dx + dy * dy) <= (radius * radius);
    },

    getBounding: HexagonalValleyNode.prototype.getBounding
};

function applyHexOverride(BaseCtor, typeString, options = {}) {
    const HexCtor = function() {
        BaseCtor.call(this);
        // Initialization tweaks for hex behavior
        this.size = options.size || [220, 220];
        this.shape = LiteGraph.BOX_SHAPE;
        this.resizable = false;
        this.movable = true; this.clonable = true; this.removable = true;
        this.flags = this.flags || {}; this.flags.collapsed = false;
        this.flags.no_panel = true; // skip default rectangular panel/title rendering
        this.title = options.title || BaseCtor.title || this.title;
        const debug = (typeof window !== "undefined" && (window.CAMPFIRE_DEBUG_ICONS ?? true));
        if (debug) {
            console.log("[HexOverride] instantiated", { intendedType: typeString, title: this.title });
        }
    };
    HexCtor.title = options.nodeTitle || BaseCtor.title;
    HexCtor.title_mode = LiteGraph.NO_TITLE; // hide default title bar on hex nodes
    HexCtor.desc = (BaseCtor.desc || "") + " (hex override)";
    HexCtor.prototype = Object.create(BaseCtor.prototype);
    HexCtor.prototype.constructor = HexCtor;
    Object.assign(HexCtor.prototype, HexNodeBaseMixin);
    // Execute logic remains from base
    if (BaseCtor.prototype.onExecute) {
        HexCtor.prototype.onExecute = BaseCtor.prototype.onExecute;
    }
    LiteGraph.registerNodeType(typeString, HexCtor);
}

// Override original node types to render as hexagons with proper connectors
applyHexOverride(ValleyNode, "campfire/valley", { title: "VALLEY" });
applyHexOverride(DockNode, "campfire/dock", { title: "DOCK" });
applyHexOverride(CampfireNode, "campfire/campfire", { title: "CAMPFIRE" });
applyHexOverride(CamperNode, "campfire/camper", { title: "CAMPER" });

// Extend hex overrides to specialized campfires and campers
applyHexOverride(DockmasterCampfireNode, "campfire/dockmaster_campfire", { title: "DOCKMASTER" });
applyHexOverride(SanitizerCampfireNode, "campfire/sanitizer_campfire", { title: "SANITIZER" });
applyHexOverride(JusticeCampfireNode, "campfire/justice_campfire", { title: "JUSTICE" });

applyHexOverride(LoaderCamperNode, "campfire/loader_camper", { title: "LOADER" });
applyHexOverride(RouterCamperNode, "campfire/router_camper", { title: "ROUTER" });
applyHexOverride(PackerCamperNode, "campfire/packer_camper", { title: "PACKER" });
applyHexOverride(ScannerCamperNode, "campfire/scanner_camper", { title: "SCANNER" });
applyHexOverride(FilterCamperNode, "campfire/filter_camper", { title: "FILTER" });
applyHexOverride(QuarantineCamperNode, "campfire/quarantine_camper", { title: "QUARANTINE" });
applyHexOverride(DetectorCamperNode, "campfire/detector_camper", { title: "DETECTOR" });
applyHexOverride(EnforcerCamperNode, "campfire/enforcer_camper", { title: "ENFORCER" });
applyHexOverride(GovernorCamperNode, "campfire/governor_camper", { title: "GOVERNOR" });