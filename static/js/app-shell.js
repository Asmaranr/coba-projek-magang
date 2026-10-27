/**
 * App Shell Controller
 * Mengelola interaksi Sidebar Otomatis (Minimize 76px default, Auto-Expand on Hover/Click, Auto-Close on Leave/Outside),
 * Navigasi Mobile, dan User Profile Dropdown di kanan atas.
 */
document.addEventListener("DOMContentLoaded", () => {
    // ============================================================
    // 1. SIDEBAR AUTO OPEN/CLOSE (TANPA TOMBOL MANUAL)
    // ============================================================
    const sidebar = document.getElementById("sidebar");

    if (sidebar) {
        // Fungsi untuk membuka sidebar (menampilkan semua label dan deskripsi)
        const expandSidebar = () => {
            sidebar.classList.add("expanded");
        };

        // Fungsi untuk menutup sidebar kembali ke mode icon-only (76px)
        const collapseSidebar = () => {
            sidebar.classList.remove("expanded");
        };

        // Buka otomatis saat kursor masuk atau menyentuh area sidebar
        sidebar.addEventListener("mouseenter", expandSidebar);

        // Buka otomatis saat area sidebar diklik
        sidebar.addEventListener("click", (e) => {
            // Cegah event bubble agar tidak langsung tertutup oleh document click
            e.stopPropagation();
            expandSidebar();
        });

        // Buka saat salah satu elemen di dalam sidebar menerima fokus keyboard
        sidebar.addEventListener("focusin", expandSidebar);

        // Tutup otomatis saat kursor meninggalkan area sidebar
        sidebar.addEventListener("mouseleave", collapseSidebar);

        // Tutup otomatis jika pengguna mengklik di luar area sidebar
        document.addEventListener("click", (e) => {
            if (!sidebar.contains(e.target)) {
                collapseSidebar();
            }
        });

        // Tutup otomatis pada perangkat layar sentuh saat pengguna menyentuh area luar sidebar
        document.addEventListener("touchstart", (e) => {
            if (!sidebar.contains(e.target)) {
                collapseSidebar();
            }
        }, { passive: true });

        // Tutup otomatis saat pengguna menggulir halaman di luar sidebar
        window.addEventListener("scroll", () => {
            collapseSidebar();
        }, { passive: true });
    }

    // ============================================================
    // 2. MOBILE SIDEBAR NAVIGATION (< 768px)
    // ============================================================
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileOverlay = document.getElementById("mobileOverlay");

    if (mobileToggle && sidebar && mobileOverlay) {
        mobileToggle.addEventListener("click", () => {
            sidebar.classList.toggle("open");
            mobileOverlay.classList.toggle("open");
        });

        mobileOverlay.addEventListener("click", () => {
            sidebar.classList.remove("open");
            mobileOverlay.classList.remove("open");
        });
    }

    // ============================================================
    // 3. USER PROFILE DROPDOWN (KANAN ATAS)
    // ============================================================
    const profileDropdown = document.getElementById("userProfileDropdown");
    const profileBtn = document.getElementById("userProfileBtn");

    if (profileDropdown && profileBtn) {
        profileBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = profileDropdown.classList.toggle("open");
            profileBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        // Tutup dropdown saat klik di luar
        document.addEventListener("click", (e) => {
            if (!profileDropdown.contains(e.target)) {
                profileDropdown.classList.remove("open");
                profileBtn.setAttribute("aria-expanded", "false");
            }
        });

        // Tutup saat menekan ESC
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && profileDropdown.classList.contains("open")) {
                profileDropdown.classList.remove("open");
                profileBtn.setAttribute("aria-expanded", "false");
            }
        });
    }
});
