// CampfireValley Gamification System - Farmville-style visual effects and mechanics

class CampfireGameEngine {
    constructor() {
        this.achievements = new Map();
        this.experiencePoints = 0;
        this.valleyLevel = 1;
        this.initializeAchievements();
    }

    // Campfire Temperature & Glow System
    calculateCampfireTemperature(efficiency, usage, queueSize) {
        // Temperature based on efficiency (0-100) and usage patterns
        const baseTemp = Math.max(20, efficiency); // Minimum smoldering temperature
        const usageBonus = Math.min(30, usage * 0.3); // Usage adds heat
        const queuePenalty = Math.min(20, queueSize * 0.5); // Too much queue cools it down
        
        return Math.min(100, baseTemp + usageBonus - queuePenalty);
    }

    getCampfireGlowIntensity(temperature) {
        // Convert temperature to glow intensity (0-1)
        return Math.max(0.2, temperature / 100);
    }

    getCampfireFlameHeight(temperature, activity) {
        // Flame height based on temperature and current activity
        const baseHeight = 10 + (temperature * 0.3);
        const activityBonus = activity ? 10 : 0;
        return baseHeight + activityBonus;
    }

    getCampfireColor(temperature) {
        // Color progression: cold blue -> warm orange -> hot white
        if (temperature < 30) {
            return { r: 100, g: 150, b: 255 }; // Cold blue
        } else if (temperature < 60) {
            const t = (temperature - 30) / 30;
            return {
                r: Math.floor(100 + t * 155), // 100 -> 255
                g: Math.floor(150 + t * 57),  // 150 -> 207
                b: Math.floor(255 - t * 200)  // 255 -> 55
            };
        } else {
            const t = (temperature - 60) / 40;
            return {
                r: 255,
                g: Math.floor(207 + t * 48),  // 207 -> 255
                b: Math.floor(55 + t * 200)   // 55 -> 255
            };
        }
    }

    // Camper Happiness & Energy System
    calculateCamperHappiness(tasksCompleted, cpuUsage, memoryUsage, errorRate) {
        let happiness = 50; // Base happiness
        
        // Task completion boosts happiness
        happiness += Math.min(30, tasksCompleted * 0.1);
        
        // High resource usage reduces happiness
        happiness -= (cpuUsage > 80 ? 20 : cpuUsage * 0.2);
        happiness -= (memoryUsage > 80 ? 15 : memoryUsage * 0.15);
        
        // Errors significantly impact happiness
        happiness -= errorRate * 25;
        
        return Math.max(0, Math.min(100, happiness));
    }

    getCamperEnergyLevel(happiness, currentTask) {
        // Energy based on happiness and whether they're working
        const baseEnergy = happiness * 0.8;
        const workingBonus = currentTask && currentTask !== "idle" ? 20 : 0;
        return Math.min(100, baseEnergy + workingBonus);
    }

    getCamperMoodEmoji(happiness) {
        if (happiness >= 80) return "😊";
        if (happiness >= 60) return "🙂";
        if (happiness >= 40) return "😐";
        if (happiness >= 20) return "😟";
        return "😢";
    }

    // Valley Prosperity System
    calculateValleyProsperity(activeCampfires, totalCampfires, avgEfficiency, totalTasks) {
        let prosperity = 0;
        
        // Campfire utilization
        const utilizationRate = activeCampfires / Math.max(1, totalCampfires);
        prosperity += utilizationRate * 40;
        
        // Average efficiency across all campfires
        prosperity += avgEfficiency * 0.4;
        
        // Total task throughput
        prosperity += Math.min(20, totalTasks * 0.01);
        
        return Math.min(100, prosperity);
    }

    getValleyGrowthStage(prosperity) {
        if (prosperity >= 90) return "flourishing";
        if (prosperity >= 70) return "thriving";
        if (prosperity >= 50) return "growing";
        if (prosperity >= 30) return "developing";
        return "struggling";
    }

    getValleyVisualElements(prosperity) {
        const stage = this.getValleyGrowthStage(prosperity);
        return {
            treeCount: Math.floor(prosperity / 20) + 1,
            flowerCount: Math.floor(prosperity / 15),
            grassDensity: prosperity / 100,
            skyColor: this.getSkyColor(prosperity),
            sunBrightness: prosperity / 100
        };
    }

    getSkyColor(prosperity) {
        // Sky gets brighter and more vibrant with prosperity
        const brightness = 150 + (prosperity * 1.05); // 150-255
        return {
            r: Math.floor(brightness * 0.6), // Soft blue
            g: Math.floor(brightness * 0.8),
            b: Math.floor(brightness)
        };
    }

    // Achievement System
    initializeAchievements() {
        this.achievements.set("first_campfire", {
            name: "First Flame",
            description: "Light your first campfire",
            icon: "🔥",
            unlocked: false,
            xp: 100
        });
        
        this.achievements.set("efficient_valley", {
            name: "Efficient Valley",
            description: "Achieve 90% efficiency across all campfires",
            icon: "⚡",
            unlocked: false,
            xp: 500
        });
        
        this.achievements.set("happy_campers", {
            name: "Happy Campers",
            description: "Keep all campers above 80% happiness",
            icon: "😊",
            unlocked: false,
            xp: 300
        });
        
        this.achievements.set("task_master", {
            name: "Task Master",
            description: "Complete 1000 tasks",
            icon: "🏆",
            unlocked: false,
            xp: 1000
        });
        
        this.achievements.set("valley_prosperity", {
            name: "Prosperous Valley",
            description: "Reach 95% valley prosperity",
            icon: "🌟",
            unlocked: false,
            xp: 750
        });
    }

    checkAchievements(gameState) {
        const unlockedAchievements = [];
        
        this.achievements.forEach((achievement, id) => {
            if (!achievement.unlocked && achievement.condition(gameState)) {
                achievement.unlocked = true;
                unlockedAchievements.push(achievement);
            }
        });
        
        return unlockedAchievements;
    }

    // Achievement notification system
    showAchievementNotification(achievement, x, y) {
        // Create floating achievement notification
        const notification = document.createElement('div');
        notification.style.position = 'fixed';
        notification.style.left = x + 'px';
        notification.style.top = y + 'px';
        notification.style.background = 'linear-gradient(45deg, #FFD700, #FFA500)';
        notification.style.color = '#000';
        notification.style.padding = '8px 12px';
        notification.style.borderRadius = '20px';
        notification.style.fontSize = '14px';
        notification.style.fontWeight = 'bold';
        notification.style.zIndex = '10000';
        notification.style.boxShadow = '0 4px 8px rgba(0,0,0,0.3)';
        notification.style.border = '2px solid #FFD700';
        notification.style.animation = 'achievementFloat 3s ease-out forwards';
        notification.textContent = `${achievement.icon} ${achievement.name}`;
        
        // Add CSS animation if not already added
        if (!document.getElementById('achievement-styles')) {
            const style = document.createElement('style');
            style.id = 'achievement-styles';
            style.textContent = `
                @keyframes achievementFloat {
                    0% { transform: translateY(0) scale(0.8); opacity: 0; }
                    20% { transform: translateY(-10px) scale(1.1); opacity: 1; }
                    80% { transform: translateY(-30px) scale(1); opacity: 1; }
                    100% { transform: translateY(-50px) scale(0.9); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(notification);
        
        // Remove notification after animation
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    // Track achievements for nodes
    trackNodeAchievements(nodeId, nodeData) {
        if (!this.nodeAchievements) {
            this.nodeAchievements = {};
        }
        
        if (!this.nodeAchievements[nodeId]) {
            this.nodeAchievements[nodeId] = new Set();
        }
        
        const gameState = {
            activeCampfires: nodeData.active ? 1 : 0,
            avgEfficiency: nodeData.efficiency || 0,
            avgCamperHappiness: nodeData.happiness || 0,
            totalTasksCompleted: nodeData.tasks_completed || 0,
            valleyProsperity: nodeData.prosperity || 0
        };
        
        const currentAchievements = this.checkAchievements(gameState);
        const newAchievements = currentAchievements.filter(
            achievement => !this.nodeAchievements[nodeId].has(achievement.name)
        );
        
        // Add new achievements and show notifications
        newAchievements.forEach(achievement => {
            this.nodeAchievements[nodeId].add(achievement.name);
            // Show notification at a random position near the center
            const x = window.innerWidth / 2 + (Math.random() - 0.5) * 200;
            const y = window.innerHeight / 2 + (Math.random() - 0.5) * 100;
            this.showAchievementNotification(achievement, x, y);
        });
        
        return newAchievements;
    }

    // Get achievement progress for display
    getAchievementProgress() {
        const total = this.achievements.size;
        const unlocked = Array.from(this.achievements.values()).filter(a => a.unlocked).length;
        return { unlocked, total, percentage: Math.round((unlocked / total) * 100) };
    }

    // Visual Effect Helpers
    drawFlameEffect(ctx, x, y, width, height, temperature, animated = true) {
        const intensity = this.getCampfireGlowIntensity(temperature);
        const color = this.getCampfireColor(temperature);
        const flameHeight = this.getCampfireFlameHeight(temperature, animated);
        
        // Create gradient for flame effect
        const gradient = ctx.createRadialGradient(
            x + width/2, y + height, 0,
            x + width/2, y + height, width/2
        );
        
        gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${intensity})`);
        gradient.addColorStop(0.5, `rgba(${Math.floor(color.r * 0.8)}, ${Math.floor(color.g * 0.6)}, ${Math.floor(color.b * 0.4)}, ${intensity * 0.7})`);
        gradient.addColorStop(1, `rgba(${Math.floor(color.r * 0.3)}, ${Math.floor(color.g * 0.2)}, ${Math.floor(color.b * 0.1)}, 0)`);
        
        ctx.fillStyle = gradient;
        
        // Draw flame shape
        ctx.beginPath();
        ctx.ellipse(x + width/2, y + height - 5, width/3, flameHeight/2, 0, 0, 2 * Math.PI);
        ctx.fill();
        
        // Add flickering effect if animated
        if (animated && temperature > 40) {
            const flicker = Math.sin(Date.now() * 0.01) * 0.1 + 0.9;
            ctx.globalAlpha = flicker;
            ctx.fill();
            ctx.globalAlpha = 1;
        }
    }

    drawGlowEffect(ctx, x, y, width, height, intensity, color) {
        const oldComposite = ctx.globalCompositeOperation;
        ctx.globalCompositeOperation = 'screen';
        
        const gradient = ctx.createRadialGradient(
            x + width/2, y + height/2, 0,
            x + width/2, y + height/2, Math.max(width, height)
        );
        
        gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${intensity * 0.3})`);
        gradient.addColorStop(0.5, `rgba(${color.r}, ${color.g}, ${color.b}, ${intensity * 0.1})`);
        gradient.addColorStop(1, `rgba(${color.r}, ${color.g}, ${color.b}, 0)`);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x - width/2, y - height/2, width * 2, height * 2);
        
        ctx.globalCompositeOperation = oldComposite;
    }

    drawProgressBar(ctx, x, y, width, height, value, maxValue, color = "#4CAF50") {
        // Background
        ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
        ctx.fillRect(x, y, width, height);
        
        // Progress
        const progress = Math.max(0, Math.min(1, value / maxValue));
        ctx.fillStyle = color;
        ctx.fillRect(x, y, width * progress, height);
        
        // Border
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, width, height);
    }
}

// Global instance
window.CampfireGameEngine = new CampfireGameEngine();