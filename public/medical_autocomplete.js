
(function () {
    "use strict";

    let medicalTestNames = [];
    let activeInput = null;
    let dropdown = null;

    async function loadTests() {
        try {
            const response = await fetch("/api/medical-test-names", {
                credentials: "same-origin",
                cache: "no-store"
            });

            if (!response.ok) return;

            const data = await response.json();

            medicalTestNames = Array.isArray(data.test_names)
                ? data.test_names
                : [];
        } catch (error) {
            console.error("Autocomplete loading failed:", error);
        }
    }

    function hideDropdown() {
        if (dropdown) {
            dropdown.style.display = "none";
        }
    }

    function selectTest(testName) {
        if (!activeInput) return;

        const currentText = activeInput.value || "";
        const match = currentText.match(/(\S+)$/);

        const updatedText = match
            ? currentText.slice(0, -match[1].length) + testName + " "
            : currentText + testName + " ";

        const setter = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype,
            "value"
        )?.set;

        if (setter) {
            setter.call(activeInput, updatedText);
        } else {
            activeInput.value = updatedText;
        }

        activeInput.dispatchEvent(
            new Event("input", { bubbles: true })
        );

        activeInput.focus();
        hideDropdown();
    }

    function showSuggestions() {
        if (!activeInput || !dropdown) return;

        const text = activeInput.value || "";
        const match = text.match(/(\S+)$/);

        if (!match || match[1].length < 2) {
            hideDropdown();
            return;
        }

        const search = match[1].toLowerCase();

        const matches = medicalTestNames
            .filter(name => name.toLowerCase().includes(search))
            .slice(0, 8);

        if (!matches.length) {
            hideDropdown();
            return;
        }

        dropdown.replaceChildren();

        for (const name of matches) {
            const item = document.createElement("div");
            item.className = "medical-autocomplete-item";
            item.textContent = name;

            item.addEventListener("mousedown", event => {
                event.preventDefault();
                selectTest(name);
            });

            dropdown.appendChild(item);
        }

        const rect = activeInput.getBoundingClientRect();

        dropdown.style.left = rect.left + "px";
        dropdown.style.width = rect.width + "px";
        dropdown.style.bottom =
            (window.innerHeight - rect.top + 8) + "px";
        dropdown.style.display = "block";
    }

    function initializeAutocomplete() {
        const input = document.querySelector(
            'textarea'
        );

        if (!input || input === activeInput) return;

        activeInput = input;

        if (!dropdown) {
            dropdown = document.createElement("div");
            dropdown.className = "medical-autocomplete-dropdown";
            document.body.appendChild(dropdown);
        }

        input.addEventListener("input", showSuggestions);
        input.addEventListener("focus", showSuggestions);
        input.addEventListener("blur", () => {
            setTimeout(hideDropdown, 150);
        });
        input.addEventListener("keydown", event => {
            if (event.key === "Escape") hideDropdown();
        });
    }

    document.addEventListener("click", event => {
        if (
            dropdown &&
            !dropdown.contains(event.target) &&
            event.target !== activeInput
        ) {
            hideDropdown();
        }
    });

    window.addEventListener("resize", hideDropdown);
    window.addEventListener("scroll", hideDropdown, true);

    const observer = new MutationObserver(initializeAutocomplete);

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    initializeAutocomplete();
    loadTests();
})();
