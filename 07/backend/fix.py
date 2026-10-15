import re  
f = open('main.py','r')  
content = f.read()  
f.close()  
content = content.replace('from .', 'from ')  
f = open('main.py','w')  
f.write(content)  
f.close()  
print('Fixed!') 
