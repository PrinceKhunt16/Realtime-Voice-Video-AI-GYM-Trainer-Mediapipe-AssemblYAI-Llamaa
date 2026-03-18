import os
import base64
import streamlit as st
from dotenv import load_dotenv

from services.ui.style_loader import inject_local_font, load_css


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def render_landing_page():
    img_path = os.path.join(BASE_DIR, "static", "IMGs", "i1.png")
    video_path = os.path.join(BASE_DIR, "static", "videos", "video.mp4")

    img_base64 = get_base64(img_path)
    video_base64 = get_base64(video_path)

    img_src = f"data:image/png;base64,{img_base64}"
    video_src = f"data:video/mp4;base64,{video_base64}"

    st.markdown(f"""
        <div class="container">
        <div class="grid-overlay"></div>

        <!-- NAV -->
        <nav class="nav">
        <div class="nav-logo">
            <span class="logo-bracket">(</span>AI GYM COACH<span class="logo-bracket">)</span>
        </div>
        <div class="nav-links">
            <a href="#visuals">Gallery</a>
            <a href="#demo">Demo</a>
            <a href="#contact">Contact</a>
        </div>
        </nav>

        <!-- HERO -->
        <section class="hero">
        <div class="hero-tag">
            <span class="dot"></span>
            <span>AI-POWERED · REAL-TIME · MOTION ANALYSIS</span>
        </div>

        <h1 class="hero-title">
            <span class="line-one">AI REAL-TIME</span>
            <span class="line-two">GYM COACH</span>
        </h1>

        <p class="hero-sub">
            Your form. Analyzed. Corrected. In milliseconds.
        </p>

        <div class="hero-cta-row">
            <a href="/workout" class="btn-primary">Try it live →</a>
            <a href="#demo" class="btn-ghost">Watch demo ↓</a>
        </div>

        <div class="metrics-strip">
            <div class="metric">
            <span class="metric-val">100<span class="unit">ms</span></span>
            <span class="metric-label">Latency</span>
            </div>
            <div class="metric-divider"></div>
            <div class="metric">
            <span class="metric-val">17+</span>
            <span class="metric-label">Joints</span>
            </div>
            <div class="metric-divider"></div>
            <div class="metric">
            <span class="metric-val">90%</span>
            <span class="metric-label">Accuracy</span>
            </div>
        </div>
        </section>

        <!-- VISUALS -->
        <section class="visuals" id="visuals">
        <div class="section-header">
            <span class="section-tag">// GALLERY</span>
            <h2 class="section-title">Built for <em>real athletes</em></h2>
        </div>

        <div class="card-grid">
            <div class="img-card">
                <div class="card-inner">
                    <div class="card-img-wrap">
                    <img src="{img_src}">
                    </div>
                    <div class="card-label">
                    <span class="card-tag">SQUAT</span>
                    <p>Form analysis</p>
                    </div>
                </div>
            </div>
        </div>
        </section>

        <!-- DEMO -->
        <section class="demo" id="demo">
        <div class="section-header">
            <span class="section-tag">// DEMO</span>
            <h2 class="section-title">See it in action</h2>
        </div>

        <div class="video-container">
            <video src="{video_src}" controls></video>
        </div>
        </section>

        <!-- CONTACT -->
        <section class="contact" id="contact">
        <div class="contact-inner">
            <h2 class="contact-title">Let's Connect</h2>
            <p class="contact-desc">Open to ML & AI roles</p>
            <a class="contact-link" href="https://www.linkedin.com/in/your-profile" target="_blank" rel="noopener noreferrer">
                linkedin.com/in/your-profile
            </a>
        </div>
        </section>
        </div>
    """, unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_title="AI GYM Coach",
        page_icon="🏋️",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    load_css(os.path.join(BASE_DIR, "static", "style.css"))
    inject_local_font(os.path.join(BASE_DIR, "static", "AdobeClean.otf"), "AdobeClean")

    render_landing_page()

if __name__ == "__main__":
    main()
