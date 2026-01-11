// Arx II Admin - Collapsible Group Functionality

(function() {
    'use strict';

    const STORAGE_KEY = 'arxAdminCollapsedGroups';

    // Load collapsed state from localStorage
    function loadCollapsedState() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            return {};
        }
    }

    // Save collapsed state to localStorage
    function saveCollapsedState(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            // Silently fail if localStorage is not available
        }
    }

    // Toggle group collapse state
    function toggleGroup(groupElement, save = true) {
        const isCollapsed = groupElement.classList.contains('collapsed');
        const content = groupElement.querySelector('.app-group-content');

        if (isCollapsed) {
            // Expand
            groupElement.classList.remove('collapsed');
            // Set max-height to scrollHeight for smooth animation
            content.style.maxHeight = content.scrollHeight + 'px';
        } else {
            // Collapse
            content.style.maxHeight = content.scrollHeight + 'px';
            // Force reflow
            content.offsetHeight;
            groupElement.classList.add('collapsed');
        }

        if (save) {
            const groupName = groupElement.dataset.group;
            const collapsedState = loadCollapsedState();
            collapsedState[groupName] = !isCollapsed;
            saveCollapsedState(collapsedState);
        }
    }

    // Initialize collapsible groups
    function initCollapsibleGroups() {
        const groups = document.querySelectorAll('.app-group');
        const collapsedState = loadCollapsedState();

        groups.forEach(group => {
            const header = group.querySelector('.app-group-header');
            const content = group.querySelector('.app-group-content');
            const groupName = group.dataset.group;

            // Set initial max-height for transitions
            if (!collapsedState[groupName]) {
                content.style.maxHeight = content.scrollHeight + 'px';
            }

            // Restore saved state
            if (collapsedState[groupName]) {
                group.classList.add('collapsed');
            }

            // Add click handler
            header.addEventListener('click', function() {
                toggleGroup(group);
            });

            // Recalculate max-height on window resize
            let resizeTimeout;
            window.addEventListener('resize', function() {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(function() {
                    if (!group.classList.contains('collapsed')) {
                        content.style.maxHeight = content.scrollHeight + 'px';
                    }
                }, 250);
            });
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCollapsibleGroups);
    } else {
        initCollapsibleGroups();
    }
})();
