"""12 — list followers and followings of an artist profile."""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

print("Followers:")
for follower in sc.get_followers("https://soundcloud.com/noisia", limit=10):
    print(" ", follower.name, follower.extra.get("followers_count"))

print("Following:")
for followed in sc.get_following("https://soundcloud.com/noisia", limit=10):
    print(" ", followed.name, followed.extra.get("followers_count"))
