goals
- provide information on lessons learned from developing Compass
- explain compass enough to understand lessons learned



Lessons





Compass Explained


Identify relevant knowledge bases
AI generates answers for each knowledge base
AI puts together all the answers



### Identify relevant knowledge bases
for each knowledge base:
1. uses retriever to get potential relevant documents
2. feeds instructions + question + potential relevant documents to AI
3. AI decides `RELEVANT` or `NOT RELEVANT`

### AI generates answers for each knowledge base
1. uses retriever to get documents that have answer to question
2. feeds question + documents + instructions to AI
3. AI generates answer

### AI puts together all the answers
1. feeds each individual answers + instructions to AI
2. AI generates answer


## Terms
- retriever
- knowledge base
- AI