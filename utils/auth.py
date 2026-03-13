import streamlit as st
from utils.database import get_or_create_user


def render_login_wall() -> bool:
    if st.session_state.get("user_id") is not None:
        return True

    st.title("🏋️‍♂️ Real-time AI GYM Trainer")
    st.markdown("### Welcome! Please enter a username to start.")

    with st.form("login_form", clear_on_submit=False):
        username_input = st.text_input("Name (unique)", placeholder="name_surname_number")
        submitted = st.form_submit_button("Start Session", use_container_width=True)

    if submitted:
        username = username_input.strip()
        
        if not username:
            st.error("Name cannot be empty.")
            return False
        
        user = get_or_create_user(username)
        
        st.session_state["user_id"] = user["id"]
        st.session_state["username"] = user["username"]
        st.rerun()

    return False
