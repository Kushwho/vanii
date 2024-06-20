from app import mongo

def store_history(sessionId, obj):
    try:
        doc = mongo.db.chat_history.find_one({"sessionId": sessionId})
        # print("I am a doc " + str(doc))
        if doc:
            mongo.db.chat_history.update_one(
                {"sessionId": sessionId},
                {"$push": {"messages": obj}}
            )
        else:
            mongo.db.chat_history.insert_one({
                "sessionId": sessionId,
                "messages": [obj]
            })
    except Exception as e:
        print(e)
