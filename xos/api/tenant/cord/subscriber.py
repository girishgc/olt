from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework import serializers
from rest_framework import generics
from rest_framework import viewsets
from rest_framework import status
from rest_framework.decorators import detail_route, list_route
from rest_framework.views import APIView
from core.models import *
from django.forms import widgets
from django.conf.urls import patterns, url
from services.volt.models import VOLTTenant, CordSubscriberRoot
from api.xosapi_helpers import PlusModelSerializer, XOSViewSet, ReadOnlyField
from django.shortcuts import get_object_or_404
from xos.apibase import XOSListCreateAPIView, XOSRetrieveUpdateDestroyAPIView, XOSPermissionDenied
from xos.exceptions import *
import json
import subprocess
from django.views.decorators.csrf import ensure_csrf_cookie

class CordSubscriberNew(CordSubscriberRoot):
    class Meta:
        proxy = True
        app_label = "cord"

    def __init__(self, *args, **kwargs):
        super(CordSubscriberNew, self).__init__(*args, **kwargs)

    def __unicode__(self):
        return u"cordSubscriber-%s" % str(self.id)

    @property
    def features(self):
        return {"cdn": self.cdn_enable,
                "uplink_speed": self.uplink_speed,
                "downlink_speed": self.downlink_speed,
                "uverse": self.enable_uverse,
                "status": self.status}

    @features.setter
    def features(self, value):
        self.cdn_enable = value.get("cdn", self.get_default_attribute("cdn_enable"))
        self.uplink_speed = value.get("uplink_speed", self.get_default_attribute("uplink_speed"))
        self.downlink_speed = value.get("downlink_speed", self.get_default_attribute("downlink_speed"))
        self.enable_uverse = value.get("uverse", self.get_default_attribute("enable_uverse"))
        self.status = value.get("status", self.get_default_attribute("status"))


    def update_features(self, value):
        d=self.features
        d.update(value)
        self.features = d

    @property
    def identity(self):
        return {"account_num": self.service_specific_id,
                "name": self.name}

    @identity.setter
    def identity(self, value):
        self.service_specific_id = value.get("account_num", self.service_specific_id)
        self.name = value.get("name", self.name)

    def update_identity(self, value):
        d=self.identity
        d.update(value)
        self.identity = d

    @property
    def related(self):
        related = {}
        if self.volt:
            related["volt_id"] = self.volt.id
            related["s_tag"] = self.volt.s_tag
            related["c_tag"] = self.volt.c_tag
            if self.volt.vcpe:
                related["vsg_id"] = self.volt.vcpe.id
                if self.volt.vcpe.instance:
                    related["instance_id"] = self.volt.vcpe.instance.id
                    related["instance_name"] = self.volt.vcpe.instance.name
                    related["wan_container_ip"] = self.volt.vcpe.wan_container_ip
                    if self.volt.vcpe.instance.node:
                         related["compute_node_name"] = self.volt.vcpe.instance.node.name
        return related

    def save(self, *args, **kwargs):
        super(CordSubscriberNew, self).save(*args, **kwargs)

class CordDevice(object):
    def __init__(self, d={}, subscriber=None):
        self.d = d
        self.subscriber = subscriber

    @property
    def mac(self):
        return self.d.get("mac", None)

    @mac.setter
    def mac(self, value):
        self.d["mac"] = value

    @property
    def identity(self):
        return {"name": self.d.get("name", None)}

    @identity.setter
    def identity(self, value):
        self.d["name"] = value.get("name", None)

    @property
    def features(self):
        return {"uplink_speed": self.d.get("uplink_speed", None),
                "downlink_speed": self.d.get("downlink_speed", None)}

    @features.setter
    def features(self, value):
        self.d["uplink_speed"] = value.get("uplink_speed", None)
        self.d["downlink_speed"] = value.get("downlink_speed", None)

    def update_features(self, value):
        d=self.features
        d.update(value)
        self.features = d

    def update_identity(self, value):
        d=self.identity
        d.update(value)
        self.identity = d

    def save(self):
        if self.subscriber:
            dev=self.subscriber.find_device(self.mac)
            if dev:
                self.subscriber.update_device(**self.d)
            else:
                self.subscriber.create_device(**self.d)

# Add some structure to the REST API by subdividing the object into
# features, identity, and related.

class FeatureSerializer(serializers.Serializer):
    cdn = serializers.BooleanField(required=False)
    uplink_speed = serializers.IntegerField(required=False)
    downlink_speed = serializers.IntegerField(required=False)
    uverse = serializers.BooleanField(required=False)
    status = serializers.CharField(required=False)

class IdentitySerializer(serializers.Serializer):
    account_num = serializers.CharField(required=False)
    name = serializers.CharField(required=False)

class DeviceFeatureSerializer(serializers.Serializer):
    uplink_speed = serializers.IntegerField(required=False)
    downlink_speed = serializers.IntegerField(required=False)

class DeviceIdentitySerializer(serializers.Serializer):
    name = serializers.CharField(required=False)

class DeviceSerializer(serializers.Serializer):
    mac = serializers.CharField(required=True)
    identity = DeviceIdentitySerializer(required=False)
    features = DeviceFeatureSerializer(required=False)

    class Meta:
        fields = ('mac', 'identity', 'features')

class CordSubscriberSerializer(PlusModelSerializer):
        id = ReadOnlyField()
        humanReadableName = serializers.SerializerMethodField("getHumanReadableName")
        features = FeatureSerializer(required=False)
        identity = IdentitySerializer(required=False)
        related = serializers.DictField(required=False)

        nested_fields = ["features", "identity"]

        class Meta:
            model = CordSubscriberNew
            fields = ('humanReadableName',
                      'id',
                      'features',
                      'identity',
                      'related')

        def getHumanReadableName(self, obj):
            return obj.__unicode__()

# @ensure_csrf_cookie
class CordSubscriberViewSet(XOSViewSet):
    base_name = "subscriber"
    method_name = "subscriber"
    method_kind = "viewset"
    queryset = CordSubscriberNew.get_tenant_objects().select_related().all()
    serializer_class = CordSubscriberSerializer

    custom_serializers = {"set_features": FeatureSerializer,
                          "set_feature": FeatureSerializer,
                          "set_identities": IdentitySerializer,
                          "set_identity": IdentitySerializer,
                          "get_devices": DeviceSerializer,
                          "add_device": DeviceSerializer,
                          "get_device_feature": DeviceFeatureSerializer,
                          "set_device_feature": DeviceFeatureSerializer}

    @classmethod
    def get_urlpatterns(self, api_path="^"):
        patterns = super(CordSubscriberViewSet, self).get_urlpatterns(api_path=api_path)
        patterns.append( self.detail_url("features/$", {"get": "get_features", "put": "set_features"}, "features") )
        patterns.append( self.detail_url("features/(?P<feature>[a-zA-Z0-9\-_]+)/$", {"get": "get_feature", "put": "set_feature"}, "get_feature") )
        patterns.append( self.detail_url("identity/$", {"get": "get_identities", "put": "set_identities"}, "identities") )
        patterns.append( self.detail_url("identity/(?P<identity>[a-zA-Z0-9\-_]+)/$", {"get": "get_identity", "put": "set_identity"}, "get_identity") )

        patterns.append( self.detail_url("devices/$", {"get": "get_devices", "post": "add_device"}, "devicees") )
        patterns.append( self.detail_url("devices/(?P<mac>[a-zA-Z0-9\-_:]+)/$", {"get": "get_device", "delete": "delete_device"}, "getset_device") )
        patterns.append( self.detail_url("devices/(?P<mac>[a-zA-Z0-9\-_:]+)/features/(?P<feature>[a-zA-Z0-9\-_]+)/$", {"get": "get_device_feature", "put": "set_device_feature"}, "getset_device_feature") )
        patterns.append( self.detail_url("devices/(?P<mac>[a-zA-Z0-9\-_:]+)/identity/(?P<identity>[a-zA-Z0-9\-_]+)/$", {"get": "get_device_identity", "put": "set_device_identity"}, "getset_device_identity") )

        patterns.append( url(self.api_path + "account_num_lookup/(?P<account_num>[0-9\-]+)/$", self.as_view({"get": "account_num_detail"}), name="account_num_detail") )

        patterns.append( url(self.api_path + "ssidmap/(?P<ssid>[0-9\-]+)/$", self.as_view({"get": "ssiddetail"}), name="ssiddetail") )
        patterns.append( url(self.api_path + "ssidmap/$", self.as_view({"get": "ssidlist"}), name="ssidlist") )

        return patterns

    def list(self, request):
        object_list = self.filter_queryset(self.get_queryset())

        serializer = self.get_serializer(object_list, many=True)

        return Response(serializer.data)

    def get_features(self, request, pk=None):
        subscriber = self.get_object()
        return Response(FeatureSerializer(subscriber.features).data)

    def set_features(self, request, pk=None):
        subscriber = self.get_object()
        ser = FeatureSerializer(subscriber.features, data=request.data)
        ser.is_valid(raise_exception = True)
        subscriber.update_features(ser.validated_data)
        subscriber.save()
        return Response(FeatureSerializer(subscriber.features).data)

    def get_feature(self, request, pk=None, feature=None):
        subscriber = self.get_object()
        return Response({feature: FeatureSerializer(subscriber.features).data[feature]})

    def set_feature(self, request, pk=None, feature=None):
        subscriber = self.get_object()
        if [feature] != request.data.keys():
             raise serializers.ValidationError("feature %s does not match keys in request body (%s)" % (feature, ",".join(request.data.keys())))
        ser = FeatureSerializer(subscriber.features, data=request.data)
        ser.is_valid(raise_exception = True)
        subscriber.update_features(ser.validated_data)
        subscriber.save()
        return Response({feature: FeatureSerializer(subscriber.features).data[feature]})

    def get_identities(self, request, pk=None):
        subscriber = self.get_object()
        return Response(IdentitySerializer(subscriber.identity).data)

    def set_identities(self, request, pk=None):
        subscriber = self.get_object()
        ser = IdentitySerializer(subscriber.identity, data=request.data)
        ser.is_valid(raise_exception = True)
        subscriber.update_identity(ser.validated_data)
        subscriber.save()
        return Response(IdentitySerializer(subscriber.identity).data)

    def get_identity(self, request, pk=None, identity=None):
        subscriber = self.get_object()
        return Response({identity: IdentitySerializer(subscriber.identity).data[identity]})

    def set_identity(self, request, pk=None, identity=None):
        subscriber = self.get_object()
        if [identity] != request.data.keys():
             raise serializers.ValidationError("identity %s does not match keys in request body (%s)" % (identity, ",".join(request.data.keys())))
        ser = IdentitySerializer(subscriber.identity, data=request.data)
        ser.is_valid(raise_exception = True)
        subscriber.update_identity(ser.validated_data)
        subscriber.save()
        return Response({identity: IdentitySerializer(subscriber.identity).data[identity]})

    def get_devices(self, request, pk=None):
        subscriber = self.get_object()
        result = []
        for device in subscriber.devices:
            device = CordDevice(device, subscriber)
            result.append(DeviceSerializer(device).data)
        return Response(result)

    def add_device(self, request, pk=None):
        subscriber = self.get_object()
        ser = DeviceSerializer(subscriber.devices, data=request.data)
        ser.is_valid(raise_exception = True)
        newdevice = CordDevice(subscriber.create_device(**ser.validated_data), subscriber)
        subscriber.save()
        return Response(DeviceSerializer(newdevice).data)

    def get_device(self, request, pk=None, mac=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        return Response(DeviceSerializer(CordDevice(device, subscriber)).data)

    def delete_device(self, request, pk=None, mac=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        subscriber.delete_device(mac)
        subscriber.save()
        return Response("Okay")

    def get_device_feature(self, request, pk=None, mac=None, feature=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        return Response({feature: DeviceFeatureSerializer(CordDevice(device, subscriber).features).data[feature]})

    def set_device_feature(self, request, pk=None, mac=None, feature=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        if [feature] != request.data.keys():
             raise serializers.ValidationError("feature %s does not match keys in request body (%s)" % (feature, ",".join(request.data.keys())))
        device = CordDevice(device, subscriber)
        ser = DeviceFeatureSerializer(device.features, data=request.data)
        ser.is_valid(raise_exception = True)
        device.update_features(ser.validated_data)
        device.save()
        subscriber.save()
        return Response({feature: DeviceFeatureSerializer(device.features).data[feature]})

    def get_device_identity(self, request, pk=None, mac=None, identity=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        return Response({identity: DeviceIdentitySerializer(CordDevice(device, subscriber).identity).data[identity]})

    def set_device_identity(self, request, pk=None, mac=None, identity=None):
        subscriber = self.get_object()
        device = subscriber.find_device(mac)
        if not device:
            return Response("Failed to find device %s" % mac, status=status.HTTP_404_NOT_FOUND)
        if [identity] != request.data.keys():
             raise serializers.ValidationError("identity %s does not match keys in request body (%s)" % (feature, ",".join(request.data.keys())))
        device = CordDevice(device, subscriber)
        ser = DeviceIdentitySerializer(device.identity, data=request.data)
        ser.is_valid(raise_exception = True)
        device.update_identity(ser.validated_data)
        device.save()
        subscriber.save()
        return Response({identity: DeviceIdentitySerializer(device.identity).data[identity]})

    def account_num_detail(self, pk=None, account_num=None):
        object_list = CordSubscriberNew.get_tenant_objects().all()
        object_list = [x for x in object_list if x.service_specific_id == account_num]
        if not object_list:
            return Response("Failed to find account_num %s" % account_num, status=status.HTTP_404_NOT_FOUND)

        return Response( object_list[0].id )

    def ssidlist(self, request):
        object_list = CordSubscriberNew.get_tenant_objects().all()

        ssidmap = [ {"service_specific_id": x.service_specific_id, "subscriber_id": x.id} for x in object_list ]

        return Response({"ssidmap": ssidmap})

    def ssiddetail(self, pk=None, ssid=None):
        object_list = CordSubscriberNew.get_tenant_objects().all()

        ssidmap = [ {"service_specific_id": x.service_specific_id, "subscriber_id": x.id} for x in object_list if str(x.service_specific_id)==str(ssid) ]

        if len(ssidmap)==0:
            raise XOSNotFound("didn't find ssid %s" % str(ssid))

        return Response( ssidmap[0] )

