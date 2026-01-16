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
        const header = groupElement.querySelector('.app-group-header');

        if (!content || !header) {
            return; // Safety check
        }

        if (isCollapsed) {
            // Expand
            groupElement.classList.remove('collapsed');
            header.setAttribute('aria-expanded', 'true');
            // Set max-height to scrollHeight for smooth animation
            try {
                content.style.maxHeight = content.scrollHeight + 'px';
            } catch (e) {
                content.style.maxHeight = 'none';
            }
        } else {
            // Collapse
            try {
                content.style.maxHeight = content.scrollHeight + 'px';
            } catch (e) {
                content.style.maxHeight = '0';
            }
            // Force reflow
            content.offsetHeight;
            groupElement.classList.add('collapsed');
            header.setAttribute('aria-expanded', 'false');
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

            if (!header || !content) {
                return; // Safety check
            }

            // Restore saved state
            if (collapsedState[groupName]) {
                group.classList.add('collapsed');
                header.setAttribute('aria-expanded', 'false');
            } else {
                // Set initial max-height for transitions (only for expanded groups)
                try {
                    content.style.maxHeight = content.scrollHeight + 'px';
                } catch (e) {
                    content.style.maxHeight = 'none';
                }
                header.setAttribute('aria-expanded', 'true');
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

// Pin button functionality
document.addEventListener('DOMContentLoaded', function() {
    const pinBtn = document.getElementById('pin-model-btn');
    if (!pinBtn) return;

    const appLabel = pinBtn.dataset.appLabel;
    const modelName = pinBtn.dataset.modelName;

    // Check current pin status
    fetch(`/admin/_pinned/?app_label=${appLabel}&model_name=${modelName}`)
        .then(r => r.json())
        .then(data => {
            updatePinButton(data.pinned);
        });

    pinBtn.addEventListener('click', function() {
        const formData = new FormData();
        formData.append('app_label', appLabel);
        formData.append('model_name', modelName);

        fetch('/admin/_pin/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
                    || getCookie('csrftoken'),
            },
        })
            .then(r => r.json())
            .then(data => {
                updatePinButton(data.pinned);
            });
    });

    function updatePinButton(pinned) {
        const textEl = pinBtn.querySelector('.pin-text');
        if (pinned) {
            pinBtn.classList.add('pinned');
            textEl.textContent = 'Unpin from Recent';
        } else {
            pinBtn.classList.remove('pinned');
            textEl.textContent = 'Pin to Recent';
        }
    }

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
});
