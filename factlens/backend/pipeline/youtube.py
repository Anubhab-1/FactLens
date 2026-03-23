import re
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def extract_video_id(url: str) -> str:
    """Extract the YouTube video ID from standard or short URLs."""
    parsed_url = urlparse(url)
    
    # Handle youtu.be short urls
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    
    # Handle standard youtube.com urls
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
        if parsed_url.path == '/watch':
            qs = parse_qs(parsed_url.query)
            return qs.get('v', [None])[0]
        elif parsed_url.path.startswith(('/embed/', '/v/', '/shorts/')):
            return parsed_url.path.split('/')[2]
            
    return None

def get_youtube_transcript(url: str) -> str:
    """
    Fetches the transcript for a YouTube video URL.
    Returns the full transcript text or raises a ValueError if none is available.
    """
    video_id = extract_video_id(url)
    
    if not video_id:
        raise ValueError("Invalid YouTube URL. Could not extract video ID.")
        
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=["en", "en-US", "en-GB"])

        # Combine text entries into a single string
        full_text = " ".join([entry.text.strip() for entry in transcript])
        
        # Clean up some common subtitle artifacts (like [Music] or newlines)
        full_text = re.sub(r'\[.*?\]', '', full_text)
        full_text = full_text.replace('\n', ' ').strip()
        full_text = re.sub(r'\s+', ' ', full_text)
        
        if not full_text:
             raise ValueError("Transcript was found but is empty.")
             
        return full_text
        
    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this YouTube video.")
    except NoTranscriptFound:
        raise ValueError("No transcript (manual or auto-generated) could be found for this video.")
    except Exception as e:
        raise ValueError(f"Failed to fetch YouTube transcript: {str(e)}")
