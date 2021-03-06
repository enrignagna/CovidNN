import tensorflow as tf
import cv2
import numpy as np
import matplotlib.pyplot as plt
from tensorflow import keras 
from keras import backend as K
from keras.models import Model


#funzione pubblica per visualizzare le heatmap calcolate.
def visualize(model, layer_name, image):
    target_size = (model.input.shape[1], model.input.shape[2])
    prediction = model.predict(image)
    classIdx = np.argmax(prediction[0])
    cam, cam3 = __compute_heatmap(model, layer_name, image, classIdx=classIdx, upsample_size=target_size)
    heatmap = __overlay_gradCAM(image,cam3)
    heatmap = heatmap[..., ::-1] # BGR to RGB
    __vis_heatmap(cam, cam3, heatmap)

#funzione pubblica per visualizzare le heatmap guided calcolate.
def visualize_guided(model, layer_name, image):
    target_size = (model.input.shape[1], model.input.shape[2])
    prediction = model.predict(image)
    classIdx = np.argmax(prediction[0])
    cam, cam3 = __compute_heatmap(model, layer_name, image, classIdx=classIdx, upsample_size=target_size)
    gh_cam = __guided_backprop(__build_guided_model(model, layer_name), image, target_size)
    guided_gradcam = __deprocess_image(gh_cam*cam3)
    gb_cam = __guided_backprop(__build_guided_model(model, layer_name), image, target_size)
    gb_im = __deprocess_image(gb_cam)
    gb_im = gb_im[..., ::-1] # BGR to RGB
    __vis_guided(guided_gradcam, gb_im)

#funzione per il calcolo delle heatmap di uno specifico livello di uno specifico modello.
def __compute_heatmap(model, layer_name, image, upsample_size, classIdx=None, eps=1e-5):
        grad_model = Model(
            inputs=[model.inputs],
            outputs=[model.get_layer(layer_name).output, model.output]
        )
        # registro le operazioni di differenziazione automatica
            
        with tf.GradientTape() as tape:
            inputs = tf.cast(image, tf.float32)
            (conv_outs, preds) = grad_model(inputs)  # predizioni dopo la softmax
            if classIdx is None:
                classIdx = np.argmax(preds)
            loss = preds[:, classIdx]
        
        # calcolo dei gradienti con la differenziazione automatica
        grads = tape.gradient(loss, conv_outs)
        # scartare la batch
        conv_outs = conv_outs[0]
        grads = grads[0]
        norm_grads = tf.divide(grads, tf.reduce_mean(tf.square(grads)) + tf.constant(eps))

        # calcolo dei pesi
        weights = tf.reduce_mean(norm_grads, axis=(0, 1))
        cam = tf.reduce_sum(tf.multiply(weights, conv_outs), axis=-1)

        # applicazione della reLU
        camR = np.maximum(cam, 0)
        camR = camR / np.max(camR)
        camR = cv2.resize(camR, upsample_size,cv2.INTER_LINEAR)

        # conversione in 3 dimensioni
        cam3 = np.expand_dims(camR, axis=2)
        cam3 = np.tile(cam3, [1, 1, 3])
        
        return cam, cam3

#funzione per l'applicazione della grad-cam sull'immagine originale.
def __overlay_gradCAM(img, cam3):
    cam3 = np.uint8(255 * cam3)
    cam3 = cv2.applyColorMap(cam3, cv2.COLORMAP_JET)

    new_img = 0.4 * cam3 / 255 + img

    return new_img

#funzione per plottare heatmap, heatmap con la relu e l'immagini con l'heatmap.
def __vis_heatmap(cam, cam3, heatmap):
    fig, ax = plt.subplots(1, 3, figsize=(15,15))
    ax[0].imshow(cam)
    ax[0].set_title("Cam")
    ax[1].imshow(cam3)
    ax[1].set_title("Cam Relu")
    ax[2].imshow(heatmap[0])
    ax[2].set_title("Image with HeatMap")
    plt.tight_layout()
    plt.show()

#funzione per plottare la grad-cam guidata e la back-propagation guidata.
def __vis_guided(guided_gradcam, guided_backprop):
    fig, ax = plt.subplots(1, 2, figsize=(10,10))
    ax[0].imshow(guided_gradcam)
    ax[0].set_title("Guided GRAD-Cam")
    ax[1].imshow(guided_backprop)
    ax[1].set_title("Guided Back-Propagation")
    plt.tight_layout()
    plt.show()


@tf.custom_gradient
def __guidedRelu(x):
    def grad(dy):
        return tf.cast(dy>0,"float32") * tf.cast(x>0, "float32") * dy
    return tf.nn.relu(x), grad

def __build_guided_model(model, layerName):
        gbModel = Model(
            inputs = [model.inputs],
            outputs = [model.get_layer(layerName).output]
        )
        layer_dict = [layer for layer in gbModel.layers[1:] if hasattr(layer,"activation")]
        for layer in layer_dict:
            if layer.activation == tf.keras.activations.relu:
                layer.activation = __guidedRelu
        
        return gbModel
    
#funzione per  la guided backpropagation per visualizzare gli input salienti.
def __guided_backprop(gbModel, images, upsample_size):
        with tf.GradientTape() as tape:
            inputs = tf.cast(images, tf.float32)
            tape.watch(inputs)
            outputs = gbModel(inputs)

        grads = tape.gradient(outputs, inputs)[0]

        saliency = cv2.resize(np.asarray(grads), upsample_size)

        return saliency

   
def __deprocess_image(x):
    # normalizzazione del tensore: centro su 0., assicura che std sia 0.25
    x = x.copy()
    x -= x.mean()
    x /= (x.std() + K.epsilon())
    x *= 0.25

    # clippa il valore tra [0, 1]
    x += 0.5
    x = np.clip(x, 0, 1)

    # conversione in array RGB
    x *= 255
    if K.image_data_format() == 'channels_first':
        x = x.transpose((1, 2, 0))
    x = np.clip(x, 0, 255).astype('uint8')
    return x