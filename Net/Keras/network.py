#
# Created on Feb, 2018
#
# @author: alexandre2r
#
# Network module: encapsulation for Keras models
#
# Based on @naxvm code:
# https://github.com/JdeRobot/dl-objectdetector
#

import os
import time
import yaml
import numpy as np
from PIL import Image
import h5py
import cv2

from keras import backend as K
from keras.models import load_model
from keras.preprocessing import image
from Net.Keras.keras_loss_function.keras_ssd_loss import SSDLoss
from Net.Keras.keras_layers.keras_layer_AnchorBoxes import AnchorBoxes
from Net.Keras.keras_layers.keras_layer_DecodeDetections import DecodeDetections
from Net.Keras.keras_layers.keras_layer_L2Normalization import L2Normalization
from Net.utils import label_map_util, create_model_from_weights


LABELS_DICT = {'voc': 'Net/labels/pascal_label_map.pbtxt',
               'coco': 'Net/labels/mscoco_label_map.pbtxt',
               'kitti': 'Net/labels/kitti_label_map.txt',
               'oid': 'Net/labels/oid_bboc_trainable_label_map.pbtxt',
               'pet': 'Net/labels/pet_label_map.pbtxt'}


class DetectionNetwork:
    def __init__(self, net_model):

        # attributes from dl-objecttracker architecture
        self.input_image = None
        self.output_image = None
        self.activated = True
        self.detection = None
        self.label = None
        self.colors = None
        self.frame = None
        # attributes set by yml config
        self.confidence_threshold = None
        # new necessary attributes from dl-objectdetector network architecture
        self.original_height = None
        self.original_width = None
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.scale = 0.5
        COLORS = label_map_util.COLORS

        self.framework = "Keras"
        self.net_has_masks = False
        self.log_network_results = []
        self.fps_network_results = []
        self.log_done = False
        self.logger_status = True
        self.image_scale = (None, None)

        # Parse the dataset to get which labels to yield
        labels_file = LABELS_DICT[net_model['Dataset'].lower()]
        label_map = label_map_util.load_labelmap(labels_file)  # loads the labels map.
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=100000)
        category_index = label_map_util.create_category_index(categories)
        self.classes = {}
        # We build is as a dict because of gaps on the labels definitions
        for cat in category_index:
            self.classes[cat] = str(category_index[cat]['name'])

        # We create the color dictionary for the bounding boxes.
        self.colors = {}
        idx = 0
        for _class in self.classes.values():
            self.colors[_class] = COLORS[idx]
            idx = + 1

        MODEL_FILE = 'Net/Keras/' + net_model['Model']

        file = h5py.File(MODEL_FILE, 'r')

        ssd_loss = SSDLoss(neg_pos_ratio=3, n_neg_min=0, alpha=1.0)

        K.clear_session()

        if str(file.items()[0][0]) == 'model_weights':
            print("Full model detected. Loading it...")
            try:
                self.model = load_model(MODEL_FILE, custom_objects={'AnchorBoxes': AnchorBoxes,
                                                               'L2Normalization': L2Normalization,
                                                               'DecodeDetections': DecodeDetections,
                                                               'compute_loss': ssd_loss.compute_loss})
            except Exception as e:
                SystemExit(e)
        else:
            print("Weights file detected. Creating a model and loading the weights into it...")
            print("Model file: ", MODEL_FILE)
            self.model = create_model_from_weights.create_model(MODEL_FILE,
                                                                ssd_loss,
                                                                len(self.classes))

        # the Keras network works on 300x300 images. Reference sizes:
        input_size = self.model.input.shape.as_list()
        self.img_height = input_size[1]
        self.img_width = input_size[2]
        # Factors to rescale the output bounding boxes
        self.height_factor = np.true_divide(self.img_height, self.img_height)
        self.width_factor = np.true_divide(self.img_width, self.img_width)

        # Output preallocation
        self.predictions = np.asarray([])
        self.boxes = np.asarray([])
        self.scores = np.asarray([])

        dummy = np.zeros([1, self.img_height, self.img_width, 3])
        self.model.predict(dummy)

        print("Network ready!")

    def predict(self):
        input_image = self.input_image
        if input_image is not None:

            start_time = time.time()

            # preprocessing
            as_image = Image.fromarray(input_image)
            resized = as_image.resize((self.img_width, self.img_height), Image.NEAREST)
            np_resized = image.img_to_array(resized)

            input_col = []
            input_col.append(np_resized)
            network_input = np.array(input_col)
            # Prediction
            y_pred = self.model.predict(network_input)

            self.label = []
            self.scores = []
            boxes = []

            # which predictions are above the confidence threshold?
            y_pred_thresh = [y_pred[k][y_pred[k,:,1] > self.confidence_threshold] for k in range(y_pred.shape[0])]
            # iterate over them
            for box in y_pred_thresh[0]:
                self.label.append(self.classes[int(box[0])])
                self.scores.append(box[1])
                xmin = int(box[2] * self.width_factor)
                ymin = int(box[3] * self.height_factor)
                xmax = int(box[4] * self.width_factor)
                ymax = int(box[5] * self.height_factor)
                boxes.append([ymin, xmin, ymax, xmax])
            self.detection = boxes

            fps_rate = 1.0 / (time.time() - start_time)  # fps calculation includes preprocessing and postprocessing

            if self.net_has_masks: #TODO: draw masks of mask nets, use tf obj det tutorial
                #from Net.utils import visualization_utils
                #print('draw mask')
                #visualization_utils.draw_mask_on_image_array(self.input_image, masks)
                #self.display_instances(self.input_image, self.detection, masks, self.label, self.scores)
                detected_image = self.renderModifiedImage(fps_rate)
            else:
                detected_image = self.renderModifiedImage(fps_rate)
            self.activated = False
            zeros = False
            # print('Detection done!')

        else:
            detected_image = np.array(np.zeros((480, 320), dtype=np.int32))  # size of images in gui
            zeros = True

        self.output_image = [detected_image, zeros]

    def renderModifiedImage(self, fps_rate):  # from utils visualize of Tensorflow folder
        image_np = np.copy(self.input_image)

        detection_boxes = self.detection
        detection_classes = self.label
        detection_scores = self.scores

        for index in range(len(detection_classes)):
            _class = detection_classes[index]
            score = detection_scores[index]
            rect = detection_boxes[index]
            xmin = rect[1]
            ymin = rect[0]
            xmax = rect[3]
            ymax = rect[2]
            cv2.rectangle(image_np, (xmin, ymin), (xmax, ymax), self.colors[_class], 3)
            # log
            if self.logger_status:
                class_no_spaces = _class.replace(" ", "")  # to allow the use of metrics calculation utility
                xmin_rescaled = int(xmin * self.image_scale[0])
                xmax_rescaled = int(xmax * self.image_scale[0])
                ymin_rescaled = int(ymin * self.image_scale[1])
                ymax_rescaled = int(ymax * self.image_scale[1])
                self.log_network_results.append([self.frame - 1, class_no_spaces, str(score), (xmin_rescaled, ymin_rescaled), (xmax_rescaled, ymax_rescaled)])
                self.fps_network_results.append(fps_rate)

            label = "{0} ({1} %)".format(_class, int(score * 100))
            [size, base] = cv2.getTextSize(label, self.font, self.scale, 2)

            points = np.array([[[xmin, ymin + base],
                                [xmin, ymin - size[1]],
                                [xmin + size[0], ymin - size[1]],
                                [xmin + size[0], ymin + base]]], dtype=np.int32)
            cv2.fillPoly(image_np, points, (0, 0, 0))
            cv2.putText(image_np, label, (xmin, ymin), self.font, self.scale, (255, 255, 255), 2)

        return image_np

    def logNetwork(self):
        if os.path.isfile('log_network.yaml') and not self.log_done:
            with open('log_network.yaml', 'w') as yamlfile:
                yaml.safe_dump(self.log_network_results, yamlfile, explicit_start=True, default_flow_style=False)
        if os.path.isfile('fps_network.yaml') and not self.log_done:
            with open('fps_network.yaml', 'w') as yamlfile:
                self.fps_network_results = round((sum(self.fps_network_results) / len(self.fps_network_results)),
                                                  3)
                yaml.safe_dump(self.fps_network_results, yamlfile, explicit_start=True, default_flow_style=False)
                self.log_done = True
            print('Log network done!')

    def setLoggerStatus(self, logger_status):
        self.logger_status = logger_status

    def setInputImage(self, im, frame_number):
        ''' Sets the input image of the network. '''
        self.input_image = im
        self.frame = frame_number
        self.original_height = im.shape[0]
        self.original_width = im.shape[1]

    def getOutputImage(self):
        ''' Returns the image with the segmented objects on it. '''
        return self.output_image

    def getProcessedFrame(self):
        ''' Returns the index of the frame processed by the net. '''
        return self.frame

    def getOutputDetection(self):
        ''' Returns the bounding boxes. '''
        return self.detection

    def getOutputLabel(self):
        ''' Returns the labels. '''
        return self.label

    def getColorList(self):
        ''' Returns the colors for the bounding boxes. '''
        return self.colors

    def toggleNetwork(self):
        ''' Toggles the network (on/off). '''
        self.activated = not self.activated
