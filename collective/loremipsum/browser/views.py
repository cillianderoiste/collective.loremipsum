import csv
import os
import time
import datetime
import logging
import random
import urllib
from htmllaundry import StripMarkup

from zope.container.interfaces import INameChooser
from zope.component import getMultiAdapter, getUtility
from zope.schema import interfaces

from zope.app.component.hooks import getSite

from plone.dexterity.interfaces import IDexterityContent
from plone.dexterity.interfaces import IDexterityFTI
from plone.app.z3cform.wysiwyg.widget import IWysiwygWidget

from Acquisition import aq_inner, aq_base
from DateTime import DateTime
from zExceptions import BadRequest

from Products.ATContentTypes.interfaces import IATEvent
from Products.Archetypes.Widget import RichWidget
from Products.Archetypes.interfaces.vocabulary import IVocabulary
from Products.Archetypes.interfaces.base import IBaseContent 
from Products.Archetypes.interfaces import field  as atfield
from Products.Archetypes.utils import addStatusMessage
from Products.Archetypes.utils import shasattr
from Products.CMFCore.WorkflowCore import WorkflowException
from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.statusmessages.interfaces import IStatusMessage

from collective.loremipsum import MessageFactory as _
from collective.loremipsum.config import BASE_URL, OPTIONS

log = logging.getLogger(__name__)

class RegisterDummyUsers(BrowserView):
    """ """

    def __call__(self, **kw):
        """ """
        site = getSite()
        mdata = getToolByName(site, 'portal_memberdata')
        regtool = getToolByName(site, 'portal_registration')
        basedir = os.path.abspath(os.path.dirname(__file__))
        datadir = os.path.join(basedir, '../dummydata')
        file = open(datadir+'/memberdata.csv')
        reader = csv.reader(file)
        row_num = 0
        for row in reader:
            if row_num == 0:
                # We will use the headers in the first row as variable names to
                # store the user's details in portal_memberdata.
                dummy_fields = row
            else:   
                properties = {}
                for field in dummy_fields:
                    # Since we don't know what properties might be in
                    # portal_memberdata, for example postal_code or zipcode or
                    # zip_code, we make give each header a list of possible values
                    # separated by spaces.
                    fields = field.split(' ')
                    for f in fields:
                        if hasattr(mdata, f):
                            properties[f] = row[dummy_fields.index(field)]

                fullname = row[0] + ' ' + row[1] 
                username = self.sanitize(fullname.lower().replace(' ', '-'))
                properties['username'] = username 
                properties['fullname'] = fullname
                try:
                    # addMember() returns MemberData object
                    member = regtool.addMember(username, 'secret', properties=properties)
                except ValueError, e:
                    # Give user visual feedback what went wrong
                    IStatusMessage(self.request).add(_(u"Could not create the users. %s" % username) + unicode(e), "error") 
                    continue
                else:
                    log.info('Registered dummy user: %s' % fullname)
            row_num += 1

        IStatusMessage(self.request).add(_(u"Succesfully created %d users." % (row_num-1)), "info") 
        return self.request.RESPONSE.redirect('/'.join(self.context.getPhysicalPath()))

    def sanitize(self, str):
        for code, ascii in [('\xc3\xbc', 'ue'), 
                            ('\xc3\xb6', 'oe'),
                            ('\xc3\xa4', 'ae'), 
                            ('\xc3\xa7', 'c'),
                            ('\xc3\xa8', 'e'), 
                            ('\xc3\xa9', 'e'),
                            ('\xc3\xab', 'e'), 
                            ('\xc3\xaf', 'i'),
                            ('\xc5\x9e', 'S'), 
                            ('\xc5\x9f', 'e'),
                            ]:
            str = str.replace(code, ascii)
            str = str.decode('utf-8').encode('ascii', 'ignore')
        return str


class CreateDummyData(BrowserView):
    """ """

    def __call__(self, **kw):
        """ 
        type: string - The portal_type of the content type to create
        amount: integer - The amount of objects to create

        ul: bool - Add unordered lists.
        ol: bool - Add numbered lists.
        dl: bool - Add description lists.
        bq: bool - Add blockquotes.
        code: bool - Add code samples.
        link: bool - Add links.
        prude: bool - Prude version.
        headers: bool - Add headers.
        allcaps: bool - Use ALL CAPS.
        decorate: bool - Add bold, italic and marked text.

        publish: bool - Should the objects be published

        recurse: bool - Should objects be created recursively?

        parnum: integer - 
            The number of paragraphs to generate. (NOT USED)

        length: short, medium, long, verylong - 
            The average length of a paragraph (NOT USED)
        """
        request = self.request
        context = aq_inner(self.context)

        types = self.request.get('type')
        if isinstance(types, str):
            types = [types]

        total = self.create_subobjects(context, 0, types)
        addStatusMessage(request, _('%d objects successfully created' % total))
        return request.RESPONSE.redirect('/'.join(context.getPhysicalPath()))


    def create_subobjects(self, context, total=0, types=None):
        request = self.request
        amount = int(request.get('amount', 3))
        if types is None:
            base = aq_base(context)
            if IBaseContent.providedBy(base):
                types = []
                if hasattr(base, 'constrainTypesMode') and base.constrainTypesMode:
                    types = context.locallyAllowedTypes
            elif IDexterityContent.providedBy(base):
                fti = getUtility(IDexterityFTI, name=context.portal_type)
                types = fti.filter_content_types and fti.allowed_content_types
                if not types:
                    msg = _('Either restrict the addable types in this folder or ' \
                            'provide a type argument.')
                    addStatusMessage(request, msg)
                    return total
            else:
                msg = _("The context doesn't provide IBaseContent or "
                        "IDexterityContent. It might be a Plone Site object, "
                        "but either way, I haven't gotten around to dealing with "
                        "it. Why don't you jump in and help?")
                addStatusMessage(request, msg)
                return total

        for portal_type in types:
            if portal_type in ['File', 'Image', 'Folder']:
                continue
                
            for n in range(0, amount):
                obj = self.create_object(context, portal_type)
                total += 1
                if request.get('recurse'):
                    total = self.create_subobjects(obj, total=total, types=None)
        return total


    def create_object(self, context, portal_type):
        """ """
        request = self.request
        url = BASE_URL + '/1/short'
        response = urllib.urlopen(url).read()
        title = StripMarkup(response.decode('utf-8')).split('.')[1]
        id= INameChooser(context).chooseName(title, context)
        try:
            id = context.invokeFactory(portal_type, id=id)
        except BadRequest:
            id += '%f' % time.time()
            id = context.invokeFactory(portal_type, id=id)
            
        obj = context[id]

        if IDexterityContent.providedBy(obj):
            if shasattr(obj, 'title'):
                obj.title = title
                self.populate_dexterity_type(obj)
        else:
            obj.setTitle(title)
            self.populate_archetype(obj)

        if request.get('publish', True):
            wftool = getToolByName(context, 'portal_workflow')
            try:
                wftool.doActionFor(obj, 'publish')
            except WorkflowException, e:
                log.error(e)

        obj.reindexObject()
        log.info('%s Object created' % obj.portal_type)
        return obj


    def get_text_line(self):
        url = BASE_URL + '/1/short'
        response = urllib.urlopen(url).read()
        return StripMarkup(response.decode('utf-8')).split('.')[1]

    def get_text_paragraph(self):
        url =  BASE_URL + '/1/short'
        response = urllib.urlopen(url).read()
        return StripMarkup(response.decode('utf-8'))

    def get_rich_text(self):
        url =  BASE_URL + '/3/short'
        for key, default in OPTIONS.items():
            if self.request.get(key, default):
                url += '/%s' % key
        return urllib.urlopen(url).read().decode('utf-8')


    def populate_dexterity_type(self, obj):
        request = self.request
        view = getMultiAdapter((obj, request), name="edit")
        view.update()
        view.form_instance.render()
        fields = view.form_instance.fields._data_values

        for i in range(0, len(fields)):
            field = fields[i].field 
            name = field.__name__

            if name == 'title':
                continue

            if interfaces.IChoice.providedBy(field):
                if shasattr(field, 'vocabulary') and field.vocabulary:
                    vocabulary = field.vocabulary
                elif shasattr(field, 'vocabularyName') and field.vocabularyName:
                    factory = getUtility(
                                    interfaces.IVocabularyFactory, 
                                    field.vocabularyName)
                    vocabulary = factory(obj)
                else:
                    continue
                index  = random.randint(0, len(vocabulary)-1)
                value = vocabulary._terms[index].value

            elif interfaces.ITextLine.providedBy(field):
                value = self.get_text_line()

            elif interfaces.IText.providedBy(field):
                widget = view.form_instance.widgets._data_values[i]

                if IWysiwygWidget.providedBy(widget):
                   value = self.get_rich_text() 
                else:
                   value = self.get_text_paragraph() 

            elif interfaces.IDatetime.providedBy(field):
                days = random.random()*10 * (random.randint(-1,1) or 1)
                value = datetime.datetime.now() + datetime.timedelta(days,0)

            elif interfaces.IDate.providedBy(field):
                days = random.random()*10 * (random.randint(-1,1) or 1)
                value = datetime.datetime.now() + datetime.timedelta(days,0)

            else:
                continue
            field.set(obj, value)


    def populate_archetype(self, obj):
        request = self.request
        fields = obj.Schema().fields()

        for field in fields:
            name = field.__name__
            if name in ['title', 'id']:
                continue

            if shasattr(field, 'vocabulary') and IVocabulary.providedBy(field.vocabulary):
                vocab = field.vocabulary.getVocabularyDict(obj)
                value = vocab.keys()[random.randint(0, len(vocab.keys())-1)]
                
            elif atfield.IStringField.providedBy(field):
                validators = [v[0].name for v in field.validators]
                if 'isURL' in validators:
                    value = 'http://en.wikipedia.com/wiki/Lorem_ipsum'
                elif 'isEmail' in validators:
                    value = 'loremipsum@mail.com'
                else:
                    value = self.get_text_line()

            elif atfield.ITextField.providedBy(field):
                widget = field.widget
                if isinstance(widget, RichWidget):
                   value = self.get_rich_text() 
                else:
                   value = self.get_text_paragraph() 

            elif atfield.IBooleanField.providedBy(field):
                value = random.randint(0,1) and True or False
            else:
                continue

            field.set(obj, value)

        if IATEvent.providedBy(obj):
            days = random.random()*20 * (random.randint(-1,1) or 1)
            value = DateTime() + days
            obj.setStartDate(value)
            obj.setEndDate(value+random.random()*3)


