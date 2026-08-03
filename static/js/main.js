document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const navToggle = document.querySelector(".nav-toggle");
    const mainNav = document.querySelector(".main-nav");

    if (navToggle && mainNav) {
        const closeMenu = () => {
            body.classList.remove("nav-open");
            navToggle.setAttribute("aria-expanded", "false");
        };

        navToggle.addEventListener("click", () => {
            const isOpen = body.classList.toggle("nav-open");
            navToggle.setAttribute("aria-expanded", String(isOpen));
        });

        mainNav.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", closeMenu);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeMenu();
        });
    }

    const revealItems = document.querySelectorAll("[data-reveal]");
    const prefersLessMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersLessMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach((item) => item.classList.add("is-visible"));
    } else {
        const revealObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("is-visible");
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.12, rootMargin: "0px 0px -40px" }
        );

        revealItems.forEach((item) => revealObserver.observe(item));
    }

    const problemField = document.querySelector("#problem");
    const exampleLinks = document.querySelectorAll("[data-example-link]");

    if (problemField && exampleLinks.length) {
        exampleLinks.forEach((link) => {
            link.addEventListener("click", () => {
                window.requestAnimationFrame(() => {
                    problemField.focus({ preventScroll: true });
                });
            });
        });
    }

    const readingProgress = document.querySelector("[data-reading-progress]");

    if (readingProgress) {
        const updateReadingProgress = () => {
            const scrollable = document.documentElement.scrollHeight - window.innerHeight;
            const progress = scrollable > 0 ? (window.scrollY / scrollable) * 100 : 0;
            readingProgress.style.width = `${Math.min(progress, 100)}%`;
        };

        window.addEventListener("scroll", updateReadingProgress, { passive: true });
        updateReadingProgress();
    }

    const copyPromptButtons = document.querySelectorAll("[data-copy-prompt]");

    copyPromptButtons.forEach((button) => {
        const defaultLabel = button.textContent;

        button.addEventListener("click", async () => {
            const prompt = button.closest(".article-prompt")?.querySelector("code");
            if (!prompt) return;

            try {
                await navigator.clipboard.writeText(prompt.textContent.trim());
                button.textContent = defaultLabel.toLowerCase().includes("пример")
                    ? "Пример скопирован"
                    : "Запрос скопирован";
                button.classList.add("is-copied");

                window.setTimeout(() => {
                    button.textContent = defaultLabel;
                    button.classList.remove("is-copied");
                }, 2200);
            } catch (error) {
                button.textContent = "Выделите текст вручную";
            }
        });
    });
});
