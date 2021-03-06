# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2014 Toyota Industrial Equipment SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import SUPERUSER_ID


def _get_args(self, args, kwargs):
    if hasattr(self, 'env'):
        cr, uid, context = self.env.args
        ids = self.ids
        vals = args[0]
    else:
        cr, uid = args[:2]
        if isinstance(args[2], dict):
            ids, vals = [], args[2]
            index = 2
        else:
            ids, vals = args[2:4]
            index = 3
        context = {}
        if index + 1 < len(args):
            context = args[index + 1]
        context = context or kwargs.get('context') or {}
    return cr, uid, ids, vals, context


def _special_wrapper(self, method, fields, *args, **kwargs):
    # Remove followers linked to old partner
    cr, uid, ids, vals, context = _get_args(self, args, kwargs)
    follower_obj = self.pool['mail.followers']
    for field in fields:
        if vals.get(field) and ids:
            partner_ids = [getattr(r, field).id for r in self.browse(cr, uid, ids, context)]
            follower_ids = follower_obj.search(cr, uid, [
                ('res_model', '=', self._name),
                ('res_id', 'in', ids),
                ('partner_id.parent_id', 'in', partner_ids),
            ], context=context)
            follower_obj.browse(cr, uid, follower_ids, context).unlink()
    res = method(self, *args, **kwargs)
    # Add followers linked to new partner
    for field in fields:
        field_to_recompute = field in self.pool.pure_function_fields
        if not field_to_recompute:
            for expr in self._fields[field].depends:
                if expr.split('.')[0] in vals:
                    field_to_recompute = True
        if field in vals or field_to_recompute:
            if hasattr(res, 'ids'):
                ids = res.ids
            records = self.pool[self._name].browse(cr, uid, ids, context)
            filter = lambda partner: self._name in [m.model for m in partner.notification_model_ids]
            for record in records:
                for contact in getattr(record, field).child_ids.filtered(filter):
                    follower_obj.create(cr, SUPERUSER_ID, {
                        'res_model': self._name,
                        'res_id': record.id,
                        'partner_id': contact.id,
                    }, context)
    return res


def add_followers(fields=['partner_id']):
    def decorator(create_or_write):
        def add_followers_wrapper(self, *args, **kwargs):
            return _special_wrapper(self, create_or_write, fields, *args, **kwargs)
        return add_followers_wrapper
    return decorator


def _add_followers(fields=['partner_id']):
    def add_followers_wrapper(self, *args, **kwargs):
        return _special_wrapper(self, add_followers_wrapper.origin, fields, *args, **kwargs)
    return add_followers_wrapper


def AddFollowers(fields=['partner_id']):
    def decorator(original_class):

        def _register_hook(self, cr):
            model_obj = self.pool.get(self._name)
            for method_name in ('create', 'write'):
                method = getattr(model_obj, method_name)
                if method.__name__ != 'add_followers_wrapper':
                    model_obj._patch_method(method_name, _add_followers(fields))
            return super(original_class, self)._register_hook(cr)

        original_class._register_hook = _register_hook
        return original_class
    return decorator
