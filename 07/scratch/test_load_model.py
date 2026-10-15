import os
import zipfile
import json
import re

os.environ['KERAS_BACKEND'] = 'torch'
import keras

keras_file = 'ml/models/footwear.keras'
with zipfile.ZipFile(keras_file, 'r') as z:
    cfg = json.loads(z.read('config.json'))

# Recursively remove BatchNormalization unsupported kwargs
def clean_config(obj):
    if isinstance(obj, dict):
        if 'config' in obj and isinstance(obj['config'], dict):
            c = obj['config']
            for k in ['renorm', 'renorm_clipping', 'renorm_momentum', 'quantization_config']:
                c.pop(k, None)
        return {k: clean_config(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_config(x) for x in obj]
    return obj

cleaned_cfg = clean_config(cfg)
print("Config cleaned successfully!")

try:
    model = keras.saving.deserialize_keras_object(cleaned_cfg)
    print("Model architecture built successfully!")
    model.load_weights('ml/models/model.weights.h5')
    print("Weights loaded successfully!")
    
    # Save a fixed model
    with zipfile.ZipFile('ml/models/footwear_fixed.keras', 'w') as z_out:
        with zipfile.ZipFile(keras_file, 'r') as z_in:
            for item in z_in.infolist():
                if item.filename == 'config.json':
                    z_out.writestr('config.json', json.dumps(cleaned_cfg))
                else:
                    z_out.writestr(item, z_in.read(item.filename))
    print("Saved ml/models/footwear_fixed.keras successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
