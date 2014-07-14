from datetime import datetime

import colander
from flask import url_for

from grano.core import db
from grano.logic import files as files_logic
from grano.logic.validation import FixedValue
from grano.model import Entity, Attribute, File


DATATYPE_TYPES = {
    'integer': colander.Integer(),
    'float': colander.Float(),
    'boolean': colander.Boolean(),
    'string': colander.String(),
    'datetime': colander.DateTime(default_tzinfo=None),
    'file': colander.String()
}


def validate_name(project, obj):
    """ Make sure that an entity's `name` attribute is unique 
    within the scope of the project. """
    def check(name):
        entity = Entity.by_name(project, name)
        if entity is not None:
            if obj is None or obj.id != entity.id:
                return False
        return True
    name_unique = colander.Function(check,
        message="An entity with this name exists")
    return colander.All(name_unique, colander.Length(min=1))


def validate(obj_type, obj, schemata, project, properties):
    """ Compile a validator for the given set of properties, based on
    the available schemata. """
    
    validator = colander.SchemaNode(colander.Mapping(), name='properties')
    for schema in schemata:
        for attr in schema.attributes:
            attrib = colander.SchemaNode(colander.Mapping(),
                name=attr.name, missing=colander.null)

            if attr.name == 'name' and obj_type == 'entity':
                attrib.add(colander.SchemaNode(colander.String(),
                    missing=colander.required, name='value',
                    validator=validate_name(project, obj)))
            else:
                T = DATATYPE_TYPES.get(attr.datatype)
                attrib.add(colander.SchemaNode(T, missing=None, name='value'))
            
            attrib.add(colander.SchemaNode(colander.Boolean(),
                default=True, missing=True, name='active'))
            attrib.add(colander.SchemaNode(FixedValue(schema), name='schema'))
            attrib.add(colander.SchemaNode(FixedValue(attr), name='attribute'))

            attrib.add(colander.SchemaNode(colander.String(),
                missing=None, name='source_url'))

            validator.add(attrib)

    properties = validator.deserialize(properties)
    out = {}
    for k, v in properties.items():
        if v != colander.null:
            out[k] = v
    return out


def save(obj, data, files=None):
    """ Set a property on the given object (entity or relation). This will
    either create a new property object or re-activate an existing object
    from the same source, if one exists. If the property is defined as 
    ``active``, existing properties with the same name will be de-activated.

    WARNING: This does not, on its own, perform any validation.
    """
    prop = None
    
    for cand in obj.properties:
        if cand.name != data.get('name'):
            continue
        if cand.value == data.get('value'):
            prop = cand
        elif cand.active and data.get('active'):
            cand.active = False

    if prop is None:
        prop = obj.PropertyClass()
        db.session.add(prop)

    prop._set_obj(obj)

    if data.get('attribute').datatype == 'file':
        # this is either a file id or the key
        # for the file data in `files`
        file_key = data.get('value')
        file = None
        file_data = None
        # TODO: validate int/string correctly with colander
        if type(file_key) in (int, long):
            file = db.session.query(File).get(file_key)
        if file is None:
            if file_key in files:
                # creates a new file
                file_data = files.get(file_key)
                file = files_logic.save(data, file_data)
            else:
                raise TypeError("File for property '%s' is required" % data.get('name'))
        prop.value_file_id = file.id
        prop.value_string = url_for('files_api.serve', id=file.id)
    else:
        setattr(prop, data.get('attribute').value_column,
            data.get('value'))

    prop.name = data.get('name')
    prop.author = data.get('author')
    prop.schema = data.get('schema')
    prop.attribute = data.get('attribute')
    prop.active = data.get('active')
    prop.source_url = data.get('source_url')
    prop.updated_at = datetime.utcnow()
    obj.updated_at = datetime.utcnow()
    return prop


def delete(prop):
    """ Delete a property. """
    db.session.delete(prop)

