// static/js/theme-switcher.js

(function() {
    'use strict';

    // 主题配置
    const THEME_KEY = 'ai-evaluation-theme';
    const LIGHT_THEME = 'light-theme';
    const DARK_THEME = 'dark-theme';
    const TRANSITION_CLASS = 'theme-transition';
    const TRANSITION_DURATION = 300;

    // 获取当前主题
    function getCurrentTheme() {
        return localStorage.getItem(THEME_KEY) || DARK_THEME;
    }

    // 设置主题
    function setTheme(theme) {
        const root = document.documentElement;
        const body = document.body;
        
        // 添加过渡类
        body.classList.add(TRANSITION_CLASS);
        
        // 移除所有主题类
        root.classList.remove(LIGHT_THEME, DARK_THEME);
        
        // 添加新主题类
        if (theme === LIGHT_THEME) {
            root.classList.add(LIGHT_THEME);
        }
        
        // 保存到本地存储
        localStorage.setItem(THEME_KEY, theme);
        
        // 更新切换按钮
        updateThemeSwitcher(theme);
        
        // 移除过渡类
        setTimeout(() => {
            body.classList.remove(TRANSITION_CLASS);
        }, TRANSITION_DURATION);
        
        // 触发自定义事件
        window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
    }

    // 更新主题切换按钮
    function updateThemeSwitcher(theme) {
        const switcher = document.querySelector('.theme-switcher');
        if (!switcher) return;
        
        const sunIcon = switcher.querySelector('.theme-icon.sun');
        const moonIcon = switcher.querySelector('.theme-icon.moon');
        const themeText = switcher.querySelector('.theme-text');
        
        if (theme === LIGHT_THEME) {
            sunIcon.style.display = 'flex';
            moonIcon.style.display = 'none';
            if (themeText) themeText.textContent = '浅色模式';
        } else {
            sunIcon.style.display = 'none';
            moonIcon.style.display = 'flex';
            if (themeText) themeText.textContent = '深色模式';
        }
    }

    // 切换主题
    function toggleTheme() {
        const currentTheme = getCurrentTheme();
        const newTheme = currentTheme === LIGHT_THEME ? DARK_THEME : LIGHT_THEME;
        setTheme(newTheme);
    }

    // 创建主题切换按钮
    function createThemeSwitcher() {
        const switcher = document.createElement('div');
        switcher.className = 'theme-switcher';
        switcher.setAttribute('role', 'button');
        switcher.setAttribute('aria-label', '切换主题');
        switcher.setAttribute('tabindex', '0');
        
        switcher.innerHTML = `
            <div class="theme-icon sun">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
            </div>
            <div class="theme-icon moon">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
            </div>
            <span class="theme-text">深色模式</span>
        `;
        
        // 添加点击事件
        switcher.addEventListener('click', toggleTheme);
        
        // 添加键盘支持
        switcher.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleTheme();
            }
        });
        
        // 添加到页面
        document.body.appendChild(switcher);
    }

    // 应用保存的主题
    function applySavedTheme() {
        const savedTheme = getCurrentTheme();
        const root = document.documentElement;
        
        // 立即应用主题，避免闪烁
        if (savedTheme === LIGHT_THEME) {
            root.classList.add(LIGHT_THEME);
        }
    }

    // 监听系统主题变化
    function watchSystemTheme() {
        if (!window.matchMedia) return;
        
        const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
        
        // 如果用户没有设置过主题，则跟随系统
        if (!localStorage.getItem(THEME_KEY)) {
            const systemTheme = mediaQuery.matches ? LIGHT_THEME : DARK_THEME;
            setTheme(systemTheme);
        }
        
        // 监听系统主题变化
        mediaQuery.addEventListener('change', (e) => {
            // 只有在用户没有手动设置主题时才跟随系统
            if (!localStorage.getItem(THEME_KEY)) {
                const systemTheme = e.matches ? LIGHT_THEME : DARK_THEME;
                setTheme(systemTheme);
            }
        });
    }

    // ECharts 主题适配
    function getEChartsTheme() {
        const currentTheme = getCurrentTheme();
        
        if (currentTheme === LIGHT_THEME) {
            return {
                color: ['#0891b2', '#7c3aed', '#ec4899', '#059669', '#d97706'],
                backgroundColor: 'transparent',
                textStyle: {
                    color: '#475569'
                },
                title: {
                    textStyle: {
                        color: '#0f172a'
                    }
                },
                legend: {
                    textStyle: {
                        color: '#475569'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(255, 255, 255, 0.95)',
                    borderColor: 'rgba(203, 213, 225, 0.7)',
                    textStyle: {
                        color: '#0f172a'
                    }
                },
                grid: {
                    borderColor: 'rgba(203, 213, 225, 0.3)'
                },
                categoryAxis: {
                    axisLine: {
                        lineStyle: {
                            color: 'rgba(203, 213, 225, 0.7)'
                        }
                    },
                    axisTick: {
                        lineStyle: {
                            color: 'rgba(203, 213, 225, 0.7)'
                        }
                    },
                    axisLabel: {
                        color: '#475569'
                    },
                    splitLine: {
                        lineStyle: {
                            color: ['rgba(203, 213, 225, 0.3)']
                        }
                    }
                },
                valueAxis: {
                    axisLine: {
                        lineStyle: {
                            color: 'rgba(203, 213, 225, 0.7)'
                        }
                    },
                    axisTick: {
                        lineStyle: {
                            color: 'rgba(203, 213, 225, 0.7)'
                        }
                    },
                    axisLabel: {
                        color: '#475569'
                    },
                    splitLine: {
                        lineStyle: {
                            color: ['rgba(203, 213, 225, 0.3)']
                        }
                    }
                }
            };
        } else {
            // 深色主题（默认）
            return {
                color: ['#00d9ff', '#7c3aed', '#ec4899', '#10b981', '#f59e0b'],
                backgroundColor: 'transparent',
                textStyle: {
                    color: '#94a3b8'
                },
                title: {
                    textStyle: {
                        color: '#ffffff'
                    }
                },
                legend: {
                    textStyle: {
                        color: '#94a3b8'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 31, 58, 0.95)',
                    borderColor: 'rgba(148, 163, 184, 0.2)',
                    textStyle: {
                        color: '#ffffff'
                    }
                },
                grid: {
                    borderColor: 'rgba(148, 163, 184, 0.1)'
                },
                categoryAxis: {
                    axisLine: {
                        lineStyle: {
                            color: 'rgba(148, 163, 184, 0.2)'
                        }
                    },
                    axisTick: {
                        lineStyle: {
                            color: 'rgba(148, 163, 184, 0.2)'
                        }
                    },
                    axisLabel: {
                        color: '#94a3b8'
                    },
                    splitLine: {
                        lineStyle: {
                            color: ['rgba(148, 163, 184, 0.1)']
                        }
                    }
                },
                valueAxis: {
                    axisLine: {
                        lineStyle: {
                            color: 'rgba(148, 163, 184, 0.2)'
                        }
                    },
                    axisTick: {
                        lineStyle: {
                            color: 'rgba(148, 163, 184, 0.2)'
                        }
                    },
                    axisLabel: {
                        color: '#94a3b8'
                    },
                    splitLine: {
                        lineStyle: {
                            color: ['rgba(148, 163, 184, 0.1)']
                        }
                    }
                }
            };
        }
    }

    // 添加平滑滚动效果
    function addSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    // 初始化
    function init() {
        // 立即应用保存的主题
        applySavedTheme();
        
        // DOM 加载完成后的操作
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', onDOMReady);
        } else {
            onDOMReady();
        }
    }

    function onDOMReady() {
        // 创建主题切换按钮
        createThemeSwitcher();
        
        // 应用主题设置
        const savedTheme = getCurrentTheme();
        updateThemeSwitcher(savedTheme);
        
        // 监听系统主题
        watchSystemTheme();
        
        // 添加平滑滚动
        addSmoothScroll();
    }

    // 暴露 API
    window.ThemeSwitcher = {
        toggle: toggleTheme,
        setTheme: setTheme,
        getCurrentTheme: getCurrentTheme,
        getEChartsTheme: getEChartsTheme
    };

    // 启动
    init();
})();
