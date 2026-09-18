/**
 * Praxis POC — Frontend JavaScript
 *
 * Handles:
 *   - AJAX bug-check submissions (no full page reload)
 *   - UI updates after solving a bug (progress, score, status)
 *   - Level-up modal display
 *
 * Phase 1:  Sends POST to /challenge/check/{bug_id} and updates the UI.
 * Future:   This may be replaced by a WebSocket connection or polling
 *           mechanism that listens for GitLab CI results.
 */

/**
 * Submit a bug check via AJAX.
 *
 * Called when the user clicks a "Check Solution" button.
 * Sends a POST request to the server and updates the UI based on the response.
 *
 * @param {number} bugId  - The database ID of the bug to check.
 * @param {HTMLElement} button - The button element that was clicked.
 */
async function checkBug(bugId, button) {
    // Prevent double-clicks
    button.disabled = true;
    button.textContent = "Evaluating...";

    try {
        const response = await fetch(`/challenge/check/${bugId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
        });

        const data = await response.json();
        
        // Show evaluation results if present
        if (data.evaluation) {
            const evalContainer = document.getElementById(`eval-result-${bugId}`);
            const evalStatus = document.getElementById(`eval-status-${bugId}`);
            const evalCommit = document.getElementById(`eval-commit-${bugId}`);
            const evalOutput = document.getElementById(`eval-output-${bugId}`);
            
            if (evalContainer) {
                evalContainer.style.display = "block";
                evalStatus.innerHTML = `<strong>Status:</strong> <span style="color: ${data.evaluation.passed ? '#a6e3a1' : '#f38ba8'}">${data.evaluation.status.toUpperCase()}</span> (Time: ${data.evaluation.execution_time.toFixed(2)}s)`;
                if (data.evaluation.commit_sha) {
                    evalCommit.innerHTML = `<strong>Commit:</strong> ${data.evaluation.commit_sha.substring(0, 8)}`;
                } else {
                    evalCommit.innerHTML = `<strong>Commit:</strong> Unknown`;
                }
                
                // Combine stdout and stderr
                let combinedOutput = "";
                if (data.evaluation.stdout) combinedOutput += data.evaluation.stdout + "\n";
                if (data.evaluation.stderr) combinedOutput += data.evaluation.stderr;
                if (!combinedOutput) combinedOutput = "No output produced.";
                
                evalOutput.textContent = combinedOutput;
            }
        }

        if (data.success && data.bug_solved) {
            // --- Bug was solved successfully ---
            updateBugCard(bugId);
            updateProgress(data.bugs_solved, data.required_bugs);
            updateScore(data.score);

            if (data.level_completed || data.all_completed) {
                // Show the level-up or completion modal
                showModal(data.message, data.all_completed);
            }
        } else if (data.already_solved) {
            // Bug was already solved — shouldn't happen normally
            button.textContent = "Already Solved";
        } else {
            // Validation error or evaluation failed
            button.textContent = "Submit Solution";
            button.disabled = false;
            // Only alert if it's not a normal evaluation failure (we show those in the UI now)
            if (!data.evaluation) {
                alert(data.message || "Something went wrong.");
            }
        }
    } catch (error) {
        // Network error
        console.error("Error checking bug:", error);
        button.textContent = "Submit Solution";
        button.disabled = false;
        alert("Network error. Please try again.");
    }
}


/**
 * Update a bug card's appearance after it's been solved.
 *
 * Changes the status icon to ✅, adds the solved CSS class,
 * and replaces the button with a "Solved" badge.
 */
function updateBugCard(bugId) {
    const card = document.getElementById(`bug-${bugId}`);
    if (!card) return;

    // Add solved styling
    card.classList.add("bug-solved", "bug-just-solved");

    // Update the status icon
    const statusIcon = card.querySelector(".status-icon");
    if (statusIcon) {
        statusIcon.textContent = "✅";
        statusIcon.classList.remove("status-unsolved");
        statusIcon.classList.add("status-solved");
    }

    // Replace the button with a badge
    const actionDiv = card.querySelector(".bug-action");
    if (actionDiv) {
        actionDiv.innerHTML = '<span class="badge badge-solved">Solved</span>';
    }
}


/**
 * Update the progress display (text and progress bar).
 */
function updateProgress(solved, required) {
    // Update text
    const progressText = document.getElementById("progress-text");
    if (progressText) {
        progressText.textContent = `${solved} / ${required}`;
    }

    // Update progress bar width
    const progressBar = document.getElementById("progress-bar");
    if (progressBar) {
        const percentage = Math.round((solved / required) * 100);
        progressBar.style.width = `${percentage}%`;
    }
}


/**
 * Update the score display.
 */
function updateScore(newScore) {
    const scoreText = document.getElementById("score-text");
    if (scoreText) {
        scoreText.textContent = newScore;
    }
}


/**
 * Show the level-up or completion modal.
 *
 * @param {string} message      - The message to display.
 * @param {boolean} allCompleted - True if all levels are done.
 */
function showModal(message, allCompleted) {
    const modal = document.getElementById("level-modal");
    const modalIcon = document.getElementById("modal-icon");
    const modalTitle = document.getElementById("modal-title");
    const modalMessage = document.getElementById("modal-message");

    if (!modal) return;

    modalIcon.textContent = allCompleted ? "🏆" : "🎉";
    modalTitle.textContent = allCompleted ? "All Levels Completed!" : "Level Completed!";
    modalMessage.textContent = message;

    modal.style.display = "flex";
}


/**
 * Close the modal and reload the page to show the next level's bugs.
 */
function closeModalAndReload() {
    const modal = document.getElementById("level-modal");
    if (modal) {
        modal.style.display = "none";
    }
    // Reload to show the next level or completion state
    window.location.reload();
}
