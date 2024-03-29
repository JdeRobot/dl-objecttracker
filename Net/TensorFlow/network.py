#
# Created on Feb, 2018
#
# @author: alexandre2r
#
# Network module: encapsulation for Tensorflow models
#
# Based on @naxvm code:
# https://github.com/JdeRobot/dl-objectdetector
#

import os
import time
import yaml
import numpy as np
import cv2
import tensorflow as tf

from Net.utils import label_map_util

LABELS_DICT = {'voc': 'Net/labels/pascal_label_map.pbtxt',
               'coco': 'Net/labels/mscoco_label_map.pbtxt',
               'kitti': 'Net/labels/kitti_label_map.txt',
               'oid': 'Net/labels/oid_bboc_trainable_label_map.pbtxt',
               'pet': 'Net/labels/pet_label_map.pbtxt'}


class DetectionNetwork:
    def __init__(self, net_model):

        # attributes from dl-objecttracker network architecture
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

        self.framework = "TensorFlow"
        self.net_has_masks = False
        self.log_network_results = []
        self.fps_network_results = []
        self.log_done = False
        self.logger_status = True
        self.image_scale = (None, None)

        labels_file = LABELS_DICT[net_model['Dataset'].lower()]
        label_map = label_map_util.load_labelmap(labels_file)  # loads the labels map.
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes= 999999)
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

        # Frozen inference graph, written on the file
        CKPT = 'Net/TensorFlow/' + net_model['Model']
        detection_graph = tf.Graph() # new graph instance.
        with detection_graph.as_default():
            od_graph_def = tf.GraphDef()
            with tf.gfile.GFile(CKPT, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                tf.import_graph_def(od_graph_def, name='')

        # Set additional parameters for the TF session
        gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.8)
        config = tf.ConfigProto(gpu_options=gpu_options,
                                log_device_placement=False)
        self.sess = tf.Session(graph=detection_graph, config=config)
        self.image_tensor = detection_graph.get_tensor_by_name('image_tensor:0')

        self.detection_boxes = detection_graph.get_tensor_by_name('detection_boxes:0')
        self.detection_scores = detection_graph.get_tensor_by_name('detection_scores:0')
        self.detection_classes = detection_graph.get_tensor_by_name('detection_classes:0')
        self.num_detections = detection_graph.get_tensor_by_name('num_detections:0')
        for op in detection_graph.get_operations():
            if op.name == 'detection_masks':
                self.net_has_masks = True
                self.detection_masks = detection_graph.get_tensor_by_name('detection_masks:0')

        self.scores = []
        self.predictions = []

        # Dummy initialization (otherwise it takes longer then)
        dummy_tensor = np.zeros((1,1,1,3), dtype=np.int32)
        if self.net_has_masks:
            self.sess.run(
                [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections, self.detection_masks],
                feed_dict={self.image_tensor: dummy_tensor})
        else:
            self.sess.run(
                    [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections],
                    feed_dict={self.image_tensor: dummy_tensor})

        print("Network ready!")

    def predict(self):
        input_image = self.input_image
        if input_image is not None:

            start_time = time.time()

            image_np_expanded = np.expand_dims(input_image, axis=0)
            if self.net_has_masks:
                (boxes, scores, predictions, _, masks) = self.sess.run(
                    [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections, self.detection_masks],
                    feed_dict={self.image_tensor: image_np_expanded})
            else:
                (boxes, scores, predictions, _) = self.sess.run(
                    [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections],
                    feed_dict={self.image_tensor: image_np_expanded})

            # We only keep the most confident predictions.
            conf = scores > self.confidence_threshold  # bool array
            boxes = boxes[conf]
            # aux variable for avoiding race condition while int casting
            tmp_boxes = np.zeros([len(boxes), 4]).astype(int)
            tmp_boxes[:, [0]] = boxes[:, [1]] * self.original_width  #xmin
            tmp_boxes[:, [2]] = boxes[:, [3]] * self.original_width  #xmax
            tmp_boxes[:, [3]] = boxes[:, [2]] * self.original_height  #ymin
            tmp_boxes[:, [1]] = boxes[:, [0]] * self.original_height  #ymax
            self.detection = tmp_boxes
            self.scores = scores[conf]
            predictions = predictions[conf].astype(int)
            self.label = []
            for pred in predictions:
                self.label.append(self.classes[pred])

            fps_rate = 1.0 / (time.time() - start_time)  # fps calculation includes preprocessing and postprocessing

            if self.net_has_masks:  #TODO: draw masks of mask nets, use tf obj det tutorial
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
            xmin = rect[0]
            ymin = rect[3]
            xmax = rect[2]
            ymax = rect[1]
            cv2.rectangle(image_np, (xmin, ymin), (xmax, ymax), self.colors[_class], 3)
            # log
            if self.logger_status:
                class_no_spaces = _class.replace(" ", "")  # to allow the use of metrics calculation utility
                xmin_rescaled = int(xmin * self.image_scale[0])
                xmax_rescaled = int(xmax * self.image_scale[0])
                ymin_rescaled = int(ymin * self.image_scale[1])
                ymax_rescaled = int(ymax * self.image_scale[1])
                self.log_network_results.append([self.frame - 1, class_no_spaces, str(score), (str(xmin_rescaled), str(ymin_rescaled)), (str(xmax_rescaled), str(ymax_rescaled))])
                self.fps_network_results.append(fps_rate)

            label = "{0} ({1} %)".format(_class, int(score*100))
            [size, base] = cv2.getTextSize(label, self.font, self.scale, 2)

            points = np.array([[[xmin, ymin + base],
                                [xmin, ymin - size[1]],
                                [xmin + size[0], ymin - size[1]],
                                [xmin + size[0], ymin + base]]], dtype=np.int32)
            cv2.fillPoly(image_np, points, (0, 0, 0))
            cv2.putText(image_np, label, (xmin, ymin), self.font, self.scale, (255, 255, 255), 2)
            cv2.putText(image_np, "neural detection", (150, 20), self.font, self.scale, (255, 0, 0), 2)

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