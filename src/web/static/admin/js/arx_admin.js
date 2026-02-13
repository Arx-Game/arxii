// Arx II Admin - Collapsible Group Functionality

// Shared utility function to get CSRF token from cookies
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

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
        .then(r => {
            if (!r.ok) throw new Error('Failed to check pin status');
            return r.json();
        })
        .then(data => {
            updatePinButton(data.pinned);
        })
        .catch(err => {
            console.error('Pin status check failed:', err);
        });

    pinBtn.addEventListener('click', function() {
        if (pinBtn.disabled) return;
        pinBtn.disabled = true;

        const formData = new FormData();
        formData.append('app_label', appLabel);
        formData.append('model_name', modelName);

        fetch('/admin/_pin/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
                    || getCookie('csrftoken') || '',
            },
        })
            .then(r => {
                if (!r.ok) throw new Error('Failed to toggle pin');
                return r.json();
            })
            .then(data => {
                updatePinButton(data.pinned);
            })
            .catch(err => {
                console.error('Pin toggle failed:', err);
            })
            .finally(() => {
                pinBtn.disabled = false;
            });
    });

    function updatePinButton(pinned) {
        const textEl = pinBtn.querySelector('.pin-text');
        pinBtn.setAttribute('aria-pressed', pinned ? 'true' : 'false');
        if (pinned) {
            pinBtn.classList.add('pinned');
            textEl.textContent = 'Unpin from Recent';
        } else {
            pinBtn.classList.remove('pinned');
            textEl.textContent = 'Pin to Recent';
        }
    }
});

// Import functionality (export is now a direct link to the preview page)
document.addEventListener('DOMContentLoaded', function() {
    const importBtn = document.getElementById('import-data-btn');
    const fileInput = document.getElementById('import-file-input');

    if (!importBtn) return;

    // Import handler - open file picker
    importBtn.addEventListener('click', function() {
        fileInput.click();
    });

    // File selected - show confirmation
    fileInput.addEventListener('change', function() {
        if (!fileInput.files || !fileInput.files[0]) return;

        const file = fileInput.files[0];
        showImportConfirmation(file);
    });

    function showImportConfirmation(file) {
        const overlay = document.createElement('div');
        overlay.className = 'import-modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'import-modal';

        const h2 = document.createElement('h2');
        h2.textContent = 'Replace All Data?';

        const p1 = document.createElement('p');
        p1.textContent = 'This will delete all existing data for models included in ';
        const strong = document.createElement('strong');
        strong.textContent = file.name;
        p1.appendChild(strong);
        p1.appendChild(document.createTextNode(' and replace it with the file contents.'));

        const p2 = document.createElement('p');
        const bold = document.createElement('strong');
        bold.textContent = 'This cannot be undone.';
        p2.appendChild(bold);

        const buttons = document.createElement('div');
        buttons.className = 'import-modal-buttons';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'import-cancel-btn';
        cancelBtn.textContent = 'Cancel';

        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = 'import-confirm-btn';
        confirmBtn.textContent = 'Replace All Data';

        buttons.appendChild(cancelBtn);
        buttons.appendChild(confirmBtn);

        modal.appendChild(h2);
        modal.appendChild(p1);
        modal.appendChild(p2);
        modal.appendChild(buttons);
        overlay.appendChild(modal);

        document.body.appendChild(overlay);

        cancelBtn.addEventListener('click', function() {
            overlay.remove();
            fileInput.value = '';
        });

        confirmBtn.addEventListener('click', function() {
            performImport(file, overlay);
        });

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                overlay.remove();
                fileInput.value = '';
            }
        });
    }

    function performImport(file, overlay) {
        const confirmBtn = overlay.querySelector('.import-confirm-btn');
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Importing...';

        const formData = new FormData();
        formData.append('file', file);

        fetch('/admin/_import/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken') || '',
            },
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(`Import successful! ${data.count} objects imported.`);
                    window.location.reload();
                } else {
                    alert(`Import failed: ${data.error}`);
                }
            })
            .catch(err => {
                alert(`Import failed: ${err.message}`);
            })
            .finally(() => {
                overlay.remove();
                fileInput.value = '';
            });
    }
});

// Export checkbox functionality
document.addEventListener('DOMContentLoaded', function() {
    const checkboxes = document.querySelectorAll('.export-checkbox');

    checkboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            const appLabel = checkbox.dataset.appLabel;
            const modelName = checkbox.dataset.modelName;

            checkbox.disabled = true;

            const formData = new FormData();
            formData.append('app_label', appLabel);
            formData.append('model_name', modelName);

            fetch('/admin/_exclude/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken') || '',
                },
            })
                .then(r => {
                    if (!r.ok) throw new Error('Failed to toggle exclusion');
                    return r.json();
                })
                .then(data => {
                    // Checkbox state should be opposite of excluded
                    checkbox.checked = !data.excluded;
                })
                .catch(err => {
                    console.error('Exclusion toggle failed:', err);
                    // Revert checkbox on error
                    checkbox.checked = !checkbox.checked;
                })
                .finally(() => {
                    checkbox.disabled = false;
                });
        });
    });
});
