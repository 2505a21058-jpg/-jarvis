from main import chat, search_experience

print("CLEAN TEST RUNNING")

while True:
    user_input = input("You: ")

    exp = search_experience(user_input)

    if exp:
        print("JARVIS (experience):", exp)
    else:
        print("JARVIS (chat):", chat(user_input, "You are JARVIS."))