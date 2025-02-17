import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from urllib.parse import urlparse
import time
import concurrent.futures

def find_gtm(html_content):
    """
    Enhanced GTM detection looking for multiple GTM implementation patterns
    """
    gtm_patterns = [
        # GTM script pattern
        r'googletagmanager\.com/gtm\.js',
        # GTM container pattern
        r'GTM-[A-Z0-9]+',
        # Google Tag Manager initialization
        r'https://www\.googletagmanager\.com/gtm\.js\?id=',
        # DataLayer initialization
        r'dataLayer\s*=\s*\[\s*\]',
        # noscript GTM implementation
        r'www\.googletagmanager\.com/ns\.html\?id=GTM-'
    ]
    
    for pattern in gtm_patterns:
        if re.search(pattern, html_content):
            return True
    return False

def extract_contact_info(soup, url):
    """Enhanced contact information extraction"""
    text = soup.get_text()
    
    # Enhanced email pattern
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails = list(set(re.findall(email_pattern, text)))
    
    # Enhanced phone pattern
    phone_pattern = r'(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    phones = list(set(re.findall(phone_pattern, text)))
    
    # Look for contact page links
    contact_links = []
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if 'contact' in href.lower() or 'about' in href.lower():
            if href.startswith('/'):
                href = f"https://{urlparse(url).netloc}{href}"
            contact_links.append(href)
    
    return {
        'emails': emails,
        'phones': phones,
        'contact_links': list(set(contact_links))
    }

def check_gtm(url):
    """Check if a website uses Google Tag Manager with enhanced error handling"""
    try:
        # Add scheme if not present
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check for GTM
        gtm_present = find_gtm(html_content)
        
        # Extract contact information
        contact_info = extract_contact_info(soup, url) if gtm_present else {'emails': [], 'phones': [], 'contact_links': []}
        
        return {
            'url': url,
            'gtm_found': gtm_present,
            'emails': contact_info['emails'],
            'phones': contact_info['phones'],
            'contact_links': contact_info['contact_links'],
            'status': 'Success' if gtm_present else 'No GTM found',
            'http_status': response.status_code
        }
            
    except requests.exceptions.SSLError:
        # Try without SSL verification
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            gtm_present = find_gtm(html_content)
            contact_info = extract_contact_info(soup, url) if gtm_present else {'emails': [], 'phones': [], 'contact_links': []}
            
            return {
                'url': url,
                'gtm_found': gtm_present,
                'emails': contact_info['emails'],
                'phones': contact_info['phones'],
                'contact_links': contact_info['contact_links'],
                'status': 'Success (SSL verification disabled)',
                'http_status': response.status_code
            }
        except Exception as e:
            return {
                'url': url,
                'gtm_found': False,
                'emails': [],
                'phones': [],
                'contact_links': [],
                'status': f'SSL Error: {str(e)}',
                'http_status': None
            }
    except Exception as e:
        return {
            'url': url,
            'gtm_found': False,
            'emails': [],
            'phones': [],
            'contact_links': [],
            'status': f'Error: {str(e)}',
            'http_status': None
        }

def main():
    st.set_page_config(page_title="Enhanced GTM Scanner", layout="wide")
    
    st.title("🔍 Google Tag Manager Website Scanner")
    st.write("This tool scans websites for GTM implementation and extracts contact details")
    
    # Add some example URLs
    st.sidebar.header("Example URLs for Testing")
    st.sidebar.write("""
    Try these websites:
    - microsoft.com
    - hubspot.com
    - salesforce.com
    - adobe.com
    - shopify.com
    """)
    
    # File upload or text input
    input_method = st.radio("Choose input method:", 
                           ["Enter URLs manually", "Upload CSV file"])
    
    urls_to_scan = []
    
    if input_method == "Enter URLs manually":
        urls_text = st.text_area(
            "Enter URLs (one per line):",
            placeholder="example.com\nanother-example.com"
        )
        if urls_text:
            urls_to_scan = [url.strip() for url in urls_text.split('\n') if url.strip()]
            
    else:
        uploaded_file = st.file_uploader("Upload CSV file with URLs", type=['csv'])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            urls_to_scan = df.iloc[:, 0].tolist()
    
    # Add scan options
    st.subheader("Scan Options")
    max_workers = st.slider("Concurrent connections", 1, 10, 3)
    timeout = st.slider("Timeout (seconds)", 5, 30, 15)
    
    if st.button("Start Scanning") and urls_to_scan:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        total_urls = len(urls_to_scan)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(check_gtm, url): url 
                           for url in urls_to_scan}
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_url):
                completed += 1
                progress = completed / total_urls
                progress_bar.progress(progress)
                status_text.text(f"Processed {completed}/{total_urls} websites")
                
                result = future.result()
                results.append(result)
                time.sleep(1)  # Rate limiting
        
        # Create DataFrame from results
        df_results = pd.DataFrame(results)
        
        # Filter successful GTM findings
        gtm_found = df_results[df_results['gtm_found']]
        
        # Display results
        st.success("Scanning completed!")
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Scanned", len(results))
        with col2:
            st.metric("GTM Found", len(gtm_found))
        with col3:
            st.metric("Success Rate", f"{(len(gtm_found)/len(results)*100):.1f}%")
        
        # Display detailed results
        if not gtm_found.empty:
            st.subheader("Detailed Results")
            for _, row in gtm_found.iterrows():
                with st.expander(f"Details for {row['url']}"):
                    st.write(f"**URL:** {row['url']}")
                    st.write(f"**Status:** {row['status']}")
                    
                    if row['emails']:
                        st.write("**Emails found:**")
                        for email in row['emails']:
                            st.write(f"- {email}")
                            
                    if row['phones']:
                        st.write("**Phone numbers found:**")
                        for phone in row['phones']:
                            st.write(f"- {phone}")
                            
                    if row['contact_links']:
                        st.write("**Contact pages found:**")
                        for link in row['contact_links']:
                            st.write(f"- {link}")
        
        # Download results
        if st.button("Download Results"):
            csv = df_results.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="gtm_scan_results.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()