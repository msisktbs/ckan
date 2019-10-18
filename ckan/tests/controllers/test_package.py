# encoding: utf-8

from bs4 import BeautifulSoup
from nose.tools import (
    assert_equal,
    assert_not_equal,
    assert_raises,
    assert_true,
    assert_not_in,
    assert_in,
)
import mock

from ckan.lib.helpers import url_for

import ckan.model as model
import ckan.model.activity as activity_model
import ckan.plugins as p
import ckan.lib.dictization as dictization
from ckan.logic.validators import object_id_validators, package_id_exists

import ckan.tests.helpers as helpers
import ckan.tests.factories as factories


webtest_submit = helpers.webtest_submit
submit_and_follow = helpers.submit_and_follow


def _get_package_new_page(app):
    user = factories.User()
    env = {'REMOTE_USER': user['name'].encode('ascii')}
    response = app.get(
        url=url_for('dataset.new'),
        extra_environ=env,
    )
    return env, response


class TestPackageNew(helpers.FunctionalTestBase):
    def test_form_renders(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        assert_true('dataset-edit' in response.forms)

    @helpers.change_config('ckan.auth.create_unowned_dataset', 'false')
    def test_needs_organization_but_no_organizations_has_button(self):
        ''' Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is allowed to create an
        organization they should be prompted to do so when they try to create
        a new dataset'''
        app = self._get_test_app()
        sysadmin = factories.Sysadmin()

        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env
        )
        assert 'dataset-edit' not in response.forms
        assert url_for(controller='organization', action='new') in response

    @helpers.mock_auth('ckan.logic.auth.create.package_create')
    @helpers.change_config('ckan.auth.create_unowned_dataset', 'false')
    @helpers.change_config('ckan.auth.user_create_organizations', 'false')
    def test_needs_organization_but_no_organizations_no_button(self,
                                                               mock_p_create):
        ''' Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is not allowed to create an
        organization they should be told to ask the admin but no link should be
        presented. Note: This cannot happen with the default ckan and requires
        a plugin to overwrite the package_create behavior'''
        mock_p_create.return_value = {'success': True}

        app = self._get_test_app()
        user = factories.User()

        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env
        )

        assert 'dataset-edit' not in response.forms
        assert url_for(controller='organization', action='new') not in response
        assert 'Ask a system administrator' in response

    def test_name_required(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']

        response = webtest_submit(form, 'save', status=200, extra_environ=env)
        assert_true('dataset-edit' in response.forms)
        assert_true('Name: Missing value' in response)

    def test_resource_form_renders(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'resource-form-renders'

        response = submit_and_follow(app, form, env, 'save')
        assert_true('resource-edit' in response.forms)

    def test_first_page_creates_draft_package(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'first-page-creates-draft'

        webtest_submit(form, 'save', status=302, extra_environ=env)
        pkg = model.Package.by_name(u'first-page-creates-draft')
        assert_equal(pkg.state, 'draft')

    def test_resource_required(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'one-resource-required'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']

        response = webtest_submit(form, 'save', value='go-metadata',
                                  status=200, extra_environ=env)
        assert_true('resource-edit' in response.forms)
        assert_true('You must add at least one data resource' in response)

    def test_complete_package_with_one_resource(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'complete-package-with-one-resource'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']
        form['url'] = u'http://example.com/resource'

        submit_and_follow(app, form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'complete-package-with-one-resource')
        assert_equal(pkg.resources[0].url, u'http://example.com/resource')
        assert_equal(pkg.state, 'active')

    def test_complete_package_with_two_resources(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'complete-package-with-two-resources'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']
        form['url'] = u'http://example.com/resource0'

        response = submit_and_follow(app, form, env, 'save', 'again')
        form = response.forms['resource-edit']
        form['url'] = u'http://example.com/resource1'

        submit_and_follow(app, form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'complete-package-with-two-resources')
        assert_equal(pkg.resources[0].url, u'http://example.com/resource0')
        assert_equal(pkg.resources[1].url, u'http://example.com/resource1')
        assert_equal(pkg.state, 'active')

    # resource upload is tested in TestExampleIUploaderPlugin

    def test_previous_button_works(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'previous-button-works'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']

        response = submit_and_follow(app, form, env, 'save', 'go-dataset')
        assert_true('dataset-edit' in response.forms)

    def test_previous_button_populates_form(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'previous-button-populates-form'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']

        response = submit_and_follow(app, form, env, 'save', 'go-dataset')
        form = response.forms['dataset-edit']
        assert_true('title' in form.fields)
        assert_equal(form['name'].value, u'previous-button-populates-form')

    def test_previous_next_maintains_draft_state(self):
        app = self._get_test_app()
        env, response = _get_package_new_page(app)
        form = response.forms['dataset-edit']
        form['name'] = u'previous-next-maintains-draft'

        response = submit_and_follow(app, form, env, 'save')
        form = response.forms['resource-edit']

        response = submit_and_follow(app, form, env, 'save', 'go-dataset')
        form = response.forms['dataset-edit']

        webtest_submit(form, 'save', status=302, extra_environ=env)
        pkg = model.Package.by_name(u'previous-next-maintains-draft')
        assert_equal(pkg.state, 'draft')

    def test_dataset_edit_org_dropdown_visible_to_normal_user_with_orgs_available(self):
        '''
        The 'Organization' dropdown is available on the dataset create/edit
        page to normal (non-sysadmin) users who have organizations available
        to them.
        '''
        user = factories.User()
        # user is admin of org.
        org = factories.Organization(
            name="my-org",
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )

        app = self._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env,
        )

        # organization dropdown available in create page.
        form = response.forms['dataset-edit']
        assert 'owner_org' in form.fields

        # create dataset
        form['name'] = u'my-dataset'
        form['owner_org'] = org['id']
        response = submit_and_follow(app, form, env, 'save')

        # add a resource to make the pkg active
        resource_form = response.forms['resource-edit']
        resource_form['url'] = u'http://example.com/resource'
        submit_and_follow(app, resource_form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'my-dataset')
        assert_equal(pkg.state, 'active')

        # edit package page response
        url = url_for('dataset.edit',
                      id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        form = pkg_edit_response.forms['dataset-edit']
        assert 'owner_org' in form.fields
        # The organization id is in the response in a value attribute
        owner_org_options = [value for (value, _) in form['owner_org'].options]
        assert org['id'] in owner_org_options

    def test_dataset_edit_org_dropdown_normal_user_can_remove_org(self):
        '''
        A normal user (non-sysadmin) can remove an organization from a dataset
        have permissions on.
        '''
        user = factories.User()
        # user is admin of org.
        org = factories.Organization(name="my-org",
                                     users=[{'name': user['id'], 'capacity': 'admin'}])

        app = self._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env,
        )

        # create dataset with owner_org
        form = response.forms['dataset-edit']
        form['name'] = u'my-dataset'
        form['owner_org'] = org['id']
        response = submit_and_follow(app, form, env, 'save')

        # add a resource to make the pkg active
        resource_form = response.forms['resource-edit']
        resource_form['url'] = u'http://example.com/resource'
        submit_and_follow(app, resource_form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'my-dataset')
        assert_equal(pkg.state, 'active')
        assert_equal(pkg.owner_org, org['id'])
        assert_not_equal(pkg.owner_org, None)

        # edit package page response
        url = url_for('dataset.edit',
                      id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)

        # edit dataset
        edit_form = pkg_edit_response.forms['dataset-edit']
        edit_form['owner_org'] = ''
        submit_and_follow(app, edit_form, env, 'save')
        post_edit_pkg = model.Package.by_name(u'my-dataset')
        assert_equal(post_edit_pkg.owner_org, None)
        assert_not_equal(post_edit_pkg.owner_org, org['id'])

    def test_dataset_edit_org_dropdown_not_visible_to_normal_user_with_no_orgs_available(self):
        '''
        The 'Organization' dropdown is not available on the dataset
        create/edit page to normal (non-sysadmin) users who have no
        organizations available to them.
        '''
        user = factories.User()
        # user isn't admin of org.
        org = factories.Organization(name="my-org")

        app = self._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env,
        )

        # organization dropdown not in create page.
        form = response.forms['dataset-edit']
        assert 'owner_org' not in form.fields

        # create dataset
        form['name'] = u'my-dataset'
        response = submit_and_follow(app, form, env, 'save')

        # add a resource to make the pkg active
        resource_form = response.forms['resource-edit']
        resource_form['url'] = u'http://example.com/resource'
        submit_and_follow(app, resource_form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'my-dataset')
        assert_equal(pkg.state, 'active')

        # edit package response
        url = url_for('dataset.edit',
                      id=model.Package.by_name(u'my-dataset').id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        form = pkg_edit_response.forms['dataset-edit']
        assert 'owner_org' not in form.fields
        # The organization id is in the response in a value attribute
        assert 'value="{0}"'.format(org['id']) not in pkg_edit_response

    def test_dataset_edit_org_dropdown_visible_to_sysadmin_with_no_orgs_available(self):
        '''
        The 'Organization' dropdown is available to sysadmin users regardless
        of whether they personally have an organization they administrate.
        '''
        user = factories.User()
        sysadmin = factories.Sysadmin()
        # user is admin of org.
        org = factories.Organization(name="my-org",
                                     users=[{'name': user['id'], 'capacity': 'admin'}])

        app = self._get_test_app()
        # user in env is sysadmin
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        response = app.get(
            url=url_for('dataset.new'),
            extra_environ=env,
        )

        # organization dropdown available in create page.
        assert 'id="field-organizations"' in response

        # create dataset
        form = response.forms['dataset-edit']
        form['name'] = u'my-dataset'
        form['owner_org'] = org['id']
        response = submit_and_follow(app, form, env, 'save')

        # add a resource to make the pkg active
        resource_form = response.forms['resource-edit']
        resource_form['url'] = u'http://example.com/resource'
        submit_and_follow(app, resource_form, env, 'save', 'go-metadata')
        pkg = model.Package.by_name(u'my-dataset')
        assert_equal(pkg.state, 'active')

        # edit package page response
        url = url_for('dataset.edit',
                      id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        assert 'id="field-organizations"' in pkg_edit_response
        # The organization id is in the response in a value attribute
        assert 'value="{0}"'.format(org['id']) in pkg_edit_response

    def test_unauthed_user_creating_dataset(self):
        app = self._get_test_app()

        # provide REMOTE_ADDR to idenfity as remote user, see
        # ckan.views.identify_user() for details
        response = app.post(url=url_for('dataset.new'),
                            extra_environ={'REMOTE_ADDR': '127.0.0.1'},
                            status=403)


class TestPackageEdit(helpers.FunctionalTestBase):
    def test_organization_admin_can_edit(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            extra_environ=env,
        )
        form = response.forms['dataset-edit']
        form['notes'] = u'edited description'
        submit_and_follow(app, form, env, 'save')

        result = helpers.call_action('package_show', id=dataset['id'])
        assert_equal(u'edited description', result['notes'])

    def test_organization_editor_can_edit(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'editor'}]
        )
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            extra_environ=env,
        )
        form = response.forms['dataset-edit']
        form['notes'] = u'edited description'
        submit_and_follow(app, form, env, 'save')

        result = helpers.call_action('package_show', id=dataset['id'])
        assert_equal(u'edited description', result['notes'])

    def test_organization_member_cannot_edit(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'member'}]
        )
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            extra_environ=env,
            status=403,
        )

    def test_user_not_in_organization_cannot_edit(self):
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            extra_environ=env,
            status=403,
        )

        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.post(
            url_for('dataset.edit',
                    id=dataset['name']),
            {'notes': 'edited description'},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_user_cannot_edit(self):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            status=403,
        )

        response = app.post(
            url_for('dataset.edit',
                    id=dataset['name']),
            {'notes': 'edited description'},
            status=403,
        )

    def test_validation_errors_for_dataset_name_appear(self):
        '''fill out a bad dataset set name and make sure errors appear'''
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=organization['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id=dataset['name']),
            extra_environ=env,
        )
        form = response.forms['dataset-edit']
        form['name'] = u'this is not a valid name'
        response = webtest_submit(form, 'save', status=200, extra_environ=env)
        assert_in('The form contains invalid entries', response.body)

        assert_in('Name: Must be purely lowercase alphanumeric (ascii) '
                  'characters and these symbols: -_', response.body)

    def test_edit_a_dataset_that_does_not_exist_404s(self):
        user = factories.User()
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.edit',
                    id='does-not-exist'),
            extra_environ=env,
            expect_errors=True
        )
        assert_equal(404, response.status_int)


class TestPackageRead(helpers.FunctionalTestBase):
    def test_read(self):
        dataset = factories.Dataset()
        app = helpers._get_test_app()
        response = app.get(url_for('dataset.read',
                                   id=dataset['name']))
        response.mustcontain('Test Dataset')
        response.mustcontain('Just another test dataset')

    def test_organization_members_can_read_private_datasets(self):
        members = {
            'member': factories.User(),
            'editor': factories.User(),
            'admin': factories.User(),
            'sysadmin': factories.Sysadmin()
        }
        organization = factories.Organization(
            users=[
                {'name': members['member']['id'], 'capacity': 'member'},
                {'name': members['editor']['id'], 'capacity': 'editor'},
                {'name': members['admin']['id'], 'capacity': 'admin'},
            ]
        )
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        app = helpers._get_test_app()

        for user, user_dict in members.items():
            response = app.get(
                url_for(
                    'dataset.read',
                    id=dataset['name']
                ),
                extra_environ={
                    'REMOTE_USER': user_dict['name'].encode('ascii'),
                },
            )
            assert_in('Test Dataset', response.body)
            assert_in('Just another test dataset', response.body)

    def test_anonymous_users_cannot_read_private_datasets(self):
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        app = helpers._get_test_app()
        response = app.get(
            url_for('dataset.read', id=dataset['name']),
            status=404
        )
        assert_equal(404, response.status_int)

    def test_user_not_in_organization_cannot_read_private_datasets(self):
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        app = helpers._get_test_app()
        response = app.get(
            url_for('dataset.read', id=dataset['name']),
            extra_environ={'REMOTE_USER': user['name'].encode('ascii')},
            status=404
        )
        assert_equal(404, response.status_int)

    def test_read_rdf(self):
        ''' The RDF outputs now live in ckanext-dcat'''
        dataset1 = factories.Dataset()

        offset = url_for('dataset.read',
                         id=dataset1['name']) + ".rdf"
        app = self._get_test_app()
        app.get(offset, status=404)

    def test_read_n3(self):
        ''' The RDF outputs now live in ckanext-dcat'''
        dataset1 = factories.Dataset()

        offset = url_for('dataset.read',
                         id=dataset1['name']) + ".n3"
        app = self._get_test_app()
        app.get(offset, status=404)

    def test_read_dataset_as_it_used_to_be(self):
        dataset = factories.Dataset(title='Original title')
        activity = model.Session.query(model.Activity) \
            .filter_by(object_id=dataset['id']) \
            .one()
        dataset['title'] = 'Changed title'
        helpers.call_action('package_update', **dataset)

        app = helpers._get_test_app()
        sysadmin = factories.Sysadmin()
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        response = app.get(url_for('dataset.read',
                                   id=dataset['name'],
                                   activity_id=activity.id),
                           extra_environ=env)
        response.mustcontain('Original title')

    def test_read_dataset_as_it_used_to_be_but_is_unmigrated(self):
        # Renders the dataset using the activity detail, when that Activity was
        # created with an earlier version of CKAN, and it has not been migrated
        # (with migrate_package_activity.py), which should give a 404
        app = self._get_test_app()

        user = factories.User()
        dataset = factories.Dataset(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = model.Session.query(model.Activity) \
            .filter_by(object_id=dataset['id']) \
            .one()
        revision_id = modern_activity.revision_id
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = 'changed'
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset['id']), context={'model': model})
        activity = model.Activity(
            user_id=user['id'],
            object_id=dataset['id'],
            revision_id=revision_id,
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                'package': dataset_table_dict,
            }
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset['id'],
            object_type=u"Package",
            activity_type=activity_type,
            data={u'package': dataset_table_dict})
        model.Session.add(activity_detail)
        model.Session.flush()

        sysadmin = factories.Sysadmin()
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        response = app.get(url_for('dataset.read',
                                   id=dataset['name'],
                                   activity_id=activity.id),
                           extra_environ=env,
                           status=404)


class TestPackageDelete(helpers.FunctionalTestBase):
    def test_owner_delete(self):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])

        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.post(
            url_for('dataset.delete', id=dataset['name']),
            extra_environ=env,
        )
        response = response.follow()
        assert_equal(200, response.status_int)

        deleted = helpers.call_action('package_show', id=dataset['id'])
        assert_equal('deleted', deleted['state'])

    def test_delete_on_non_existing_dataset(self):
        app = helpers._get_test_app()
        response = app.post(
            url_for('dataset.delete',
                    id='schrodingersdatset'),
            expect_errors=True,
        )
        assert_equal(404, response.status_int)

    def test_sysadmin_can_delete_any_dataset(self):
        owner_org = factories.Organization()
        dataset = factories.Dataset(owner_org=owner_org['id'])
        app = helpers._get_test_app()

        user = factories.Sysadmin()
        env = {'REMOTE_USER': user['name'].encode('ascii')}

        response = app.post(
            url_for('dataset.delete', id=dataset['name']),
            extra_environ=env,
        )
        response = response.follow()
        assert_equal(200, response.status_int)

        deleted = helpers.call_action('package_show', id=dataset['id'])
        assert_equal('deleted', deleted['state'])

    def test_anon_user_cannot_delete_owned_dataset(self):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])

        app = helpers._get_test_app()
        response = app.post(
            url_for('dataset.delete', id=dataset['name']),
            status=403,
        )
        response.mustcontain('Unauthorized to delete package')

        deleted = helpers.call_action('package_show', id=dataset['id'])
        assert_equal('active', deleted['state'])

    def test_logged_in_user_cannot_delete_owned_dataset(self):
        owner = factories.User()
        owner_org = factories.Organization(
            users=[{'name': owner['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])

        app = helpers._get_test_app()
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.post(
            url_for('dataset.delete', id=dataset['name']),
            extra_environ=env,
            expect_errors=True
        )
        assert_equal(403, response.status_int)
        response.mustcontain('Unauthorized to delete package')

    def test_confirm_cancel_delete(self):
        '''Test confirmation of deleting datasets

        When package_delete is made as a get request, it should return a
        'do you want to delete this dataset? confirmation page'''
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])

        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('dataset.delete', id=dataset['name']),
            extra_environ=env,
        )
        assert_equal(200, response.status_int)
        message = 'Are you sure you want to delete dataset - {name}?'
        response.mustcontain(message.format(name=dataset['title']))

        form = response.forms['confirm-dataset-delete-form']
        response = form.submit('cancel')
        response = helpers.webtest_maybe_follow(
            response,
            extra_environ=env,
        )
        assert_equal(200, response.status_int)


class TestResourceNew(helpers.FunctionalTestBase):
    def test_manage_dataset_resource_listing_page(self):
        user = factories.User()
        organization = factories.Organization(user=user)
        dataset = factories.Dataset(owner_org=organization['id'])
        resource = factories.Resource(package_id=dataset['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for(
                'dataset.resources',
                id=dataset['name'],
            ),
            extra_environ=env
        )
        assert_in(resource['name'], response)
        assert_in(resource['description'], response)
        assert_in(resource['format'], response)

    def test_unauth_user_cannot_view_manage_dataset_resource_listing_page(self):
        user = factories.User()
        organization = factories.Organization(user=user)
        dataset = factories.Dataset(owner_org=organization['id'])
        resource = factories.Resource(package_id=dataset['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for(
                'dataset.resources',
                id=dataset['name'],
            ),
            extra_environ=env
        )
        assert_in(resource['name'], response)
        assert_in(resource['description'], response)
        assert_in(resource['format'], response)

    def test_404_on_manage_dataset_resource_listing_page_that_does_not_exist(self):
        user = factories.User()
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for(
                'dataset.resources',
                id='does-not-exist'
            ),
            extra_environ=env,
            expect_errors=True
        )
        assert_equal(404, response.status_int)

    def test_add_new_resource_with_link_and_download(self):
        user = factories.User()
        dataset = factories.Dataset()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            extra_environ=env
        )

        form = response.forms['resource-edit']
        form['url'] = u'http://test.com/'
        response = submit_and_follow(app, form, env, 'save',
                                     'go-dataset-complete')

        result = helpers.call_action('package_show', id=dataset['id'])
        response = app.get(
            url_for(
                'resource.download',
                id=dataset['id'],
                resource_id=result['resources'][0]['id']
            ),
            extra_environ=env,
        )
        assert_equal(302, response.status_int)

    def test_editor_can_add_new_resource(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'editor'}]
        )
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            extra_environ=env
        )

        form = response.forms['resource-edit']
        form['name'] = u'test resource'
        form['url'] = u'http://test.com/'
        response = submit_and_follow(app, form, env, 'save',
                                     'go-dataset-complete')

        result = helpers.call_action('package_show', id=dataset['id'])
        assert_equal(1, len(result['resources']))
        assert_equal(u'test resource', result['resources'][0]['name'])

    def test_admin_can_add_new_resource(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            extra_environ=env
        )

        form = response.forms['resource-edit']
        form['name'] = u'test resource'
        form['url'] = u'http://test.com/'
        response = submit_and_follow(app, form, env, 'save',
                                     'go-dataset-complete')

        result = helpers.call_action('package_show', id=dataset['id'])
        assert_equal(1, len(result['resources']))
        assert_equal(u'test resource', result['resources'][0]['name'])

    def test_member_cannot_add_new_resource(self):
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'member'}]
        )
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            {'name': 'test', 'url': 'test', 'save': 'save', 'id': ''},
            extra_environ=env,
            status=403,
        )

    def test_non_organization_users_cannot_add_new_resource(self):
        '''on an owned dataset'''
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            {'name': 'test', 'url': 'test', 'save': 'save', 'id': ''},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_users_cannot_add_new_resource(self):
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        app = helpers._get_test_app()

        response = app.get(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            status=403,
        )

        response = app.post(
            url_for(
                'resource.new',
                id=dataset['id'],
            ),
            {'name': 'test', 'url': 'test', 'save': 'save', 'id': ''},
            status=403,
        )

    def test_anonymous_users_cannot_edit_resource(self):
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
        )
        resource = factories.Resource(package_id=dataset['id'])
        app = helpers._get_test_app()

        with app.flask_app.test_request_context():
            response = app.get(
                url_for(
                    'resource.edit',
                    id=dataset['id'],
                    resource_id=resource['id'],
                ),
                status=403,
            )

            response = app.post(
                url_for(
                    'resource.edit',
                    id=dataset['id'],
                    resource_id=resource['id'],
                ),
                {'name': 'test', 'url': 'test', 'save': 'save', 'id': ''},
                status=403,
            )


class TestResourceView(helpers.FunctionalTestBase):
    @classmethod
    def _apply_config_changes(cls, cfg):
        cfg['ckan.plugins'] = 'image_view'

    @classmethod
    def setup_class(cls):
        super(cls, cls).setup_class()

        if not p.plugin_loaded('image_view'):
            p.load('image_view')
        helpers.reset_db()

    @classmethod
    def teardown_class(cls):
        p.unload('image_view')

    def test_resource_view_create(self):
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}

        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        url = url_for('resource.edit_view',
                      id=resource['package_id'],
                      resource_id=resource['id'],
                      view_type='image_view')

        app = self._get_test_app()
        response = app.post(
            url, {'title': 'Test Image View'}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain('Test Image View')

    def test_resource_view_edit(self):
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}

        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        resource_view = factories.ResourceView(resource_id=resource['id'])
        url = url_for('resource.edit_view',
                      id=resource_view['package_id'],
                      resource_id=resource_view['resource_id'],
                      view_id=resource_view['id'])

        app = self._get_test_app()
        response = app.post(
            url, {'title': 'Updated RV Title'}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain('Updated RV Title')

    def test_resource_view_delete(self):
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}

        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        resource_view = factories.ResourceView(resource_id=resource['id'])
        url = url_for('resource.edit_view',
                      id=resource_view['package_id'],
                      resource_id=resource_view['resource_id'],
                      view_id=resource_view['id'])

        app = self._get_test_app()
        response = app.post(
            url, {'delete': 'Delete'}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain('This resource has no views')

    def test_existent_resource_view_page_returns_ok_code(self):
        resource_view = factories.ResourceView()

        url = url_for('resource.read',
                      id=resource_view['package_id'],
                      resource_id=resource_view['resource_id'],
                      view_id=resource_view['id'])

        app = self._get_test_app()
        app.get(url, status=200)

    def test_inexistent_resource_view_page_returns_not_found_code(self):
        resource_view = factories.ResourceView()

        url = url_for('resource.read',
                      id=resource_view['package_id'],
                      resource_id=resource_view['resource_id'],
                      view_id='inexistent-view-id')

        app = self._get_test_app()
        app.get(url, status=404)

    def test_resource_view_description_is_rendered_as_markdown(self):
        resource_view = factories.ResourceView(description="Some **Markdown**")
        url = url_for('resource.read',
                      id=resource_view['package_id'],
                      resource_id=resource_view['resource_id'],
                      view_id=resource_view['id'])
        app = self._get_test_app()
        response = app.get(url)
        response.mustcontain('Some <strong>Markdown</strong>')


class TestResourceRead(helpers.FunctionalTestBase):
    def test_existing_resource_with_not_associated_dataset(self):

        dataset = factories.Dataset()
        resource = factories.Resource()

        url = url_for('resource.read',
                      id=dataset['id'],
                      resource_id=resource['id'])

        app = self._get_test_app()
        app.get(url, status=404)

    def test_resource_read_logged_in_user(self):
        '''
        A logged-in user can view resource page.
        '''
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset['id'])

        url = url_for('resource.read',
                      id=dataset['id'],
                      resource_id=resource['id'])

        app = self._get_test_app()
        app.get(url, status=200, extra_environ=env)

    def test_resource_read_anon_user(self):
        '''
        An anon user can view resource page.
        '''
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset['id'])

        url = url_for('resource.read',
                      id=dataset['id'],
                      resource_id=resource['id'])

        app = self._get_test_app()
        app.get(url, status=200)

    def test_resource_read_sysadmin(self):
        '''
        A sysadmin can view resource page.
        '''
        sysadmin = factories.Sysadmin()
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset['id'])

        url = url_for('resource.read',
                      id=dataset['id'],
                      resource_id=resource['id'])

        app = self._get_test_app()
        app.get(url, status=200, extra_environ=env)

    def test_user_not_in_organization_cannot_read_private_dataset(self):
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        resource = factories.Resource(package_id=dataset['id'])

        url = url_for('resource.read',
                      id=dataset['id'],
                      resource_id=resource['id'])

        app = self._get_test_app()
        response = app.get(url,
                           status=404,
                           extra_environ=env)

    def test_organization_members_can_read_resources_in_private_datasets(self):
        members = {
            'member': factories.User(),
            'editor': factories.User(),
            'admin': factories.User(),
            'sysadmin': factories.Sysadmin()
        }
        organization = factories.Organization(
            users=[
                {'name': members['member']['id'], 'capacity': 'member'},
                {'name': members['editor']['id'], 'capacity': 'editor'},
                {'name': members['admin']['id'], 'capacity': 'admin'},
            ]
        )
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        resource = factories.Resource(package_id=dataset['id'])

        app = helpers._get_test_app()

        for user, user_dict in members.items():
            response = app.get(
                url_for(
                    'resource.read',
                    id=dataset['name'],
                    resource_id=resource['id'],
                ),
                extra_environ={
                    'REMOTE_USER': user_dict['name'].encode('ascii'),
                },
            )
            assert_in('Just another test resource', response.body)

    def test_anonymous_users_cannot_read_private_datasets(self):
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        app = helpers._get_test_app()
        response = app.get(
            url_for('dataset.read', id=dataset['name']),
            status=404
        )
        assert_equal(404, response.status_int)


class TestResourceDelete(helpers.FunctionalTestBase):
    def test_dataset_owners_can_delete_resources(self):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.post(
            url_for('resource.delete',
                    id=dataset['name'], resource_id=resource['id']),
            extra_environ=env,
        )
        response = response.follow()
        assert_equal(200, response.status_int)
        response.mustcontain('This dataset has no data')

        assert_raises(p.toolkit.ObjectNotFound, helpers.call_action,
                      'resource_show', id=resource['id'])

    def test_deleting_non_existing_resource_404s(self):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()
        response = app.post(
            url_for('resource.delete',
                    id=dataset['name'], resource_id='doesnotexist'),
            extra_environ=env,
            expect_errors=True
        )
        assert_equal(404, response.status_int)

    def test_anon_users_cannot_delete_owned_resources(self):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        app = helpers._get_test_app()
        response = app.post(
            url_for('resource.delete',
                    id=dataset['name'], resource_id=resource['id']),
            status=403,
        )
        response.mustcontain('Unauthorized to delete package')

    def test_logged_in_users_cannot_delete_resources_they_do_not_own(self):
        # setup our dataset
        owner = factories.User()
        owner_org = factories.Organization(
            users=[{'name': owner['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        # access as another user
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app = helpers._get_test_app()
        response = app.post(
            url_for('resource.delete',
                    id=dataset['name'], resource_id=resource['id']),
            extra_environ=env,
            expect_errors=True
        )
        assert_equal(403, response.status_int)
        response.mustcontain('Unauthorized to delete package')

    def test_sysadmins_can_delete_any_resource(self):
        owner_org = factories.Organization()
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])

        sysadmin = factories.Sysadmin()
        app = helpers._get_test_app()
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        response = app.post(
            url_for('resource.delete',
                    id=dataset['name'], resource_id=resource['id']),
            extra_environ=env,
        )
        response = response.follow()
        assert_equal(200, response.status_int)
        response.mustcontain('This dataset has no data')

        assert_raises(p.toolkit.ObjectNotFound, helpers.call_action,
                      'resource_show', id=resource['id'])

    def test_confirm_and_cancel_deleting_a_resource(self):
        '''Test confirmation of deleting resources

        When resource_delete is made as a get request, it should return a
        'do you want to delete this reource? confirmation page'''
        user = factories.User()
        owner_org = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=owner_org['id'])
        resource = factories.Resource(package_id=dataset['id'])
        app = helpers._get_test_app()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(
            url_for('resource.delete',
                    id=dataset['name'], resource_id=resource['id']),
            extra_environ=env,
        )
        assert_equal(200, response.status_int)
        message = 'Are you sure you want to delete resource - {name}?'
        response.mustcontain(message.format(name=resource['name']))

        # cancelling sends us back to the resource edit page
        form = response.forms['confirm-resource-delete-form']
        response = form.submit('cancel')
        response = response.follow(extra_environ=env)
        assert_equal(200, response.status_int)


class TestSearch(helpers.FunctionalTestBase):
    def test_search_basic(self):
        dataset1 = factories.Dataset()

        offset = url_for('dataset.search')
        app = self._get_test_app()
        page = app.get(offset)

        assert dataset1['name'] in page.body.decode('utf8')

    def test_search_language_toggle(self):
        dataset1 = factories.Dataset()

        app = self._get_test_app()
        with app.flask_app.test_request_context():
            offset = url_for(
                'dataset.search', q=dataset1['name'])
        page = app.get(offset)

        assert dataset1['name'] in page.body.decode('utf8')
        assert ('q=' + dataset1['name']) in page.body.decode('utf8')

    def test_search_sort_by_blank(self):
        factories.Dataset()

        # ?sort has caused an exception in the past
        offset = url_for('dataset.search') + '?sort'
        app = self._get_test_app()
        app.get(offset)

    def test_search_sort_by_bad(self):
        factories.Dataset()

        # bad spiders try all sorts of invalid values for sort. They should get
        # a 400 error with specific error message. No need to alert the
        # administrator.
        offset = url_for('dataset.search') + \
            '?sort=gvgyr_fgevat+nfp'
        app = self._get_test_app()
        response = app.get(offset, status=[200, 400])
        if response.status == 200:
            import sys
            sys.stdout.write(response.body)
            raise Exception("Solr returned an unknown error message. "
                            "Please check the error handling "
                            "in ckan/lib/search/query.py:run")

    def test_search_solr_syntax_error(self):
        factories.Dataset()

        # SOLR raises SyntaxError when it can't parse q (or other fields?).
        # Whilst this could be due to a bad user input, it could also be
        # because CKAN mangled things somehow and therefore we flag it up to
        # the administrator and give a meaningless error, just in case
        offset = url_for('dataset.search') + \
            '?q=--included'
        app = self._get_test_app()
        search_response = app.get(offset)

        search_response_html = BeautifulSoup(search_response.body)
        err_msg = search_response_html.select('#search-error')
        err_msg = ''.join([n.text for n in err_msg])
        assert_in('error while searching', err_msg)

    def test_search_plugin_hooks(self):
        with p.use_plugin('test_package_controller_plugin') as plugin:

            offset = url_for('dataset.search')
            app = self._get_test_app()
            app.get(offset)

            # get redirected ...
            assert plugin.calls['before_search'] == 1, plugin.calls
            assert plugin.calls['after_search'] == 1, plugin.calls

    def test_search_page_request(self):
        '''Requesting package search page returns list of datasets.'''
        app = self._get_test_app()
        factories.Dataset(name="dataset-one", title='Dataset One')
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        search_url = url_for('dataset.search')
        search_response = app.get(search_url)

        assert_true('3 datasets found' in search_response)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        ds_titles = [n.string for n in ds_titles]

        assert_equal(len(ds_titles), 3)
        assert_true('Dataset One' in ds_titles)
        assert_true('Dataset Two' in ds_titles)
        assert_true('Dataset Three' in ds_titles)

    def test_search_page_results(self):
        '''Searching for datasets returns expected results.'''
        app = self._get_test_app()
        factories.Dataset(name="dataset-one", title='Dataset One')
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        search_url = url_for('dataset.search')
        search_response = app.get(search_url)

        search_form = search_response.forms['dataset-search-form']
        search_form['q'] = 'One'
        search_results = webtest_submit(search_form)

        assert_true('1 dataset found' in search_results)

        search_response_html = BeautifulSoup(search_results.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        ds_titles = [n.string for n in ds_titles]

        assert_equal(len(ds_titles), 1)
        assert_true('Dataset One' in ds_titles)

    def test_search_page_no_results(self):
        '''Search with non-returning phrase returns no results.'''
        app = self._get_test_app()
        factories.Dataset(name="dataset-one", title='Dataset One')
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        search_url = url_for('dataset.search')
        search_response = app.get(search_url)

        search_form = search_response.forms['dataset-search-form']
        search_form['q'] = 'Nout'
        search_results = webtest_submit(search_form)

        assert_true('No datasets found for "Nout"' in search_results)

        search_response_html = BeautifulSoup(search_results.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        ds_titles = [n.string for n in ds_titles]

        assert_equal(len(ds_titles), 0)

    def test_search_page_results_tag(self):
        '''Searching with a tag returns expected results.'''
        app = self._get_test_app()
        factories.Dataset(name="dataset-one", title='Dataset One',
                          tags=[{'name': 'my-tag'}])
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        search_url = url_for('dataset.search')
        search_response = app.get(search_url)
        assert_true('/dataset/?tags=my-tag' in search_response)

        tag_search_response = app.get('/dataset?tags=my-tag')

        assert_true('1 dataset found' in tag_search_response)

        search_response_html = BeautifulSoup(tag_search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        ds_titles = [n.string for n in ds_titles]

        assert_equal(len(ds_titles), 1)
        assert_true('Dataset One' in ds_titles)

    def test_search_page_results_tags(self):
        '''Searching with a tag returns expected results with multiple tags'''

        app = self._get_test_app()
        factories.Dataset(name="dataset-one", title='Dataset One',
                          tags=[
                              {'name': 'my-tag-1'},
                              {'name': 'my-tag-2'},
                              {'name': 'my-tag-3'},
                          ])
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        params = '/dataset/?tags=my-tag-1&tags=my-tag-2&tags=my-tag-3'
        tag_search_response = app.get(params)

        assert_true('1 dataset found' in tag_search_response)

        search_response_html = BeautifulSoup(tag_search_response.body)
        ds_titles = search_response_html.select('.filtered')
        assert_equal(len(ds_titles), 3)

    def test_search_page_results_private(self):
        '''Private datasets don't show up in dataset search results.'''
        app = self._get_test_app()
        org = factories.Organization()

        factories.Dataset(name="dataset-one", title='Dataset One',
                          owner_org=org['id'], private=True)
        factories.Dataset(name="dataset-two", title='Dataset Two')
        factories.Dataset(name="dataset-three", title='Dataset Three')

        search_url = url_for('dataset.search')
        search_response = app.get(search_url)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        ds_titles = [n.string for n in ds_titles]

        assert_equal(len(ds_titles), 2)
        assert_true('Dataset One' not in ds_titles)
        assert_true('Dataset Two' in ds_titles)
        assert_true('Dataset Three' in ds_titles)

    def test_user_not_in_organization_cannot_search_private_datasets(self):
        app = helpers._get_test_app()
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        search_url = url_for('dataset.search')
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        assert_equal([n.string for n in ds_titles], [])

    def test_user_in_organization_can_search_private_datasets(self):
        app = helpers._get_test_app()
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'member'}])
        dataset = factories.Dataset(
            title='A private dataset',
            owner_org=organization['id'],
            private=True,
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        search_url = url_for('dataset.search')
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        assert_equal([n.string for n in ds_titles], ['A private dataset'])

    def test_user_in_different_organization_cannot_search_private_datasets(self):
        app = helpers._get_test_app()
        user = factories.User()
        org1 = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'member'}])
        org2 = factories.Organization()
        dataset = factories.Dataset(
            title='A private dataset',
            owner_org=org2['id'],
            private=True,
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        search_url = url_for('dataset.search')
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        assert_equal([n.string for n in ds_titles], [])

    @helpers.change_config('ckan.search.default_include_private', 'false')
    def test_search_default_include_private_false(self):
        app = helpers._get_test_app()
        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'member'}])
        dataset = factories.Dataset(
            owner_org=organization['id'],
            private=True,
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        search_url = url_for('dataset.search')
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        assert_equal([n.string for n in ds_titles], [])

    def test_sysadmin_can_search_private_datasets(self):
        app = helpers._get_test_app()
        user = factories.Sysadmin()
        organization = factories.Organization()
        dataset = factories.Dataset(
            title='A private dataset',
            owner_org=organization['id'],
            private=True,
        )
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        search_url = url_for('dataset.search')
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select('.dataset-list '
                                                '.dataset-item '
                                                '.dataset-heading a')
        assert_equal([n.string for n in ds_titles], ['A private dataset'])


class TestPackageFollow(helpers.FunctionalTestBase):

    def test_package_follow(self):
        app = self._get_test_app()

        user = factories.User()
        package = factories.Dataset()

        env = {'REMOTE_USER': user['name'].encode('ascii')}
        follow_url = url_for('dataset.follow',
                             id=package['id'])
        response = app.post(follow_url, extra_environ=env, status=302)
        response = response.follow()
        assert_true('You are now following {0}'
                    .format(package['title'])
                    in response)

    def test_package_follow_not_exist(self):
        '''Pass an id for a package that doesn't exist'''
        app = self._get_test_app()

        user_one = factories.User()

        env = {'REMOTE_USER': user_one['name'].encode('ascii')}
        follow_url = url_for('dataset.follow',
                             id='not-here')
        response = app.post(follow_url, extra_environ=env, status=302)
        response = response.follow(status=404)
        assert_true('Dataset not found' in response)

    def test_package_unfollow(self):
        app = self._get_test_app()

        user_one = factories.User()
        package = factories.Dataset()

        env = {'REMOTE_USER': user_one['name'].encode('ascii')}
        follow_url = url_for('dataset.follow',
                             id=package['id'])
        app.post(follow_url, extra_environ=env, status=302)

        unfollow_url = url_for('dataset.unfollow',
                               id=package['id'])
        unfollow_response = app.post(unfollow_url, extra_environ=env,
                                     status=302)
        unfollow_response = unfollow_response.follow()

        assert_true('You are no longer following {0}'
                    .format(package['title'])
                    in unfollow_response)

    def test_package_unfollow_not_following(self):
        '''Unfollow a package not currently following'''
        app = self._get_test_app()

        user_one = factories.User()
        package = factories.Dataset()

        env = {'REMOTE_USER': user_one['name'].encode('ascii')}
        unfollow_url = url_for('dataset.unfollow',
                               id=package['id'])
        unfollow_response = app.post(unfollow_url, extra_environ=env,
                                     status=302)
        unfollow_response = unfollow_response.follow()  # /package/[id] 302s to
        unfollow_response = unfollow_response.follow()  # /package/[name]

        assert_true('You are not following {0}'.format(package['id'])
                    in unfollow_response)

    def test_package_unfollow_not_exist(self):
        '''Unfollow a package that doesn't exist.'''
        app = self._get_test_app()

        user_one = factories.User()

        env = {'REMOTE_USER': user_one['name'].encode('ascii')}
        unfollow_url = url_for('dataset.unfollow',
                               id='not-here')
        unfollow_response = app.post(unfollow_url, extra_environ=env,
                                     status=302)
        unfollow_response = unfollow_response.follow(status=404)
        assert_true('Dataset not found' in unfollow_response)

    def test_package_follower_list(self):
        '''Following users appear on followers list page.'''
        app = self._get_test_app()

        user_one = factories.Sysadmin()
        package = factories.Dataset()

        env = {'REMOTE_USER': user_one['name'].encode('ascii')}
        follow_url = url_for('dataset.follow',
                             id=package['id'])
        app.post(follow_url, extra_environ=env, status=302)

        followers_url = url_for('dataset.followers',
                                id=package['id'])

        # Only sysadmins can view the followers list pages
        followers_response = app.get(followers_url, extra_environ=env,
                                     status=200)
        assert_true(user_one['display_name'] in followers_response)


class TestDatasetRead(helpers.FunctionalTestBase):

    def test_dataset_read(self):
        app = self._get_test_app()

        dataset = factories.Dataset()

        url = url_for('dataset.read',
                      id=dataset['name'])
        response = app.get(url)
        assert_in(dataset['title'], response)

    def test_redirect_when_given_id(self):
        dataset = factories.Dataset()
        app = helpers._get_test_app()
        response = app.get(url_for('dataset.read', id=dataset['id']),
                           status=302)
        # redirect replaces the ID with the name in the URL
        redirected_response = response.follow()
        expected_url = url_for('dataset.read', id=dataset['name'])
        assert_equal(redirected_response.request.path, expected_url)
        assert_equal(redirected_response.request.query_string, '')

    def test_redirect_also_with_activity_parameter(self):
        dataset = factories.Dataset()
        activity = activity_model.package_activity_list(dataset['id'], limit=1,
                                                        offset=0)[0]
        # view as an admin because viewing the old versions of a dataset
        sysadmin = factories.Sysadmin()
        env = {'REMOTE_USER': sysadmin['name'].encode('ascii')}
        app = helpers._get_test_app()
        response = app.get(url_for('dataset.read', id=dataset['id'],
                                   activity_id=activity.id),
                           status=302, extra_environ=env)
        redirected_response = response.follow(extra_environ=env)
        expected_path = url_for('dataset.read', id=dataset['name'])
        assert_equal(redirected_response.request.path, expected_path)
        assert_equal(redirected_response.request.query_string,
                     'activity_id={}'.format(activity.id))

    def test_no_redirect_loop_when_name_is_the_same_as_the_id(self):
        dataset = factories.Dataset(id='abc', name='abc')
        app = helpers._get_test_app()
        app.get(url_for('dataset.read', id=dataset['id']),
                status=200)  # ie no redirect


class TestActivity(helpers.FunctionalTestBase):
    def test_simple(self):
        '''Checking the template shows the activity stream.'''
        app = self._get_test_app()
        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_in('Mr. Test User', response)
        assert_in('created the dataset', response)

    def test_create_dataset(self):
        app = self._get_test_app()
        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_in('<a href="/user/{}">Mr. Test User'.format(user['name']),
                  response)
        assert_in('created the dataset', response)
        assert_in('<a href="/dataset/{}">Test Dataset'.format(dataset['id']),
                  response)

    def _clear_activities(self):
        model.Session.query(model.Activity).delete()
        model.Session.flush()

    def test_change_dataset(self):
        app = self._get_test_app()
        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        dataset['title'] = 'Dataset with changed title'
        helpers.call_action(
            'package_update', context={'user': user['name']}, **dataset)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_in('<a href="/user/{}">Mr. Test User'.format(user['name']),
                  response)
        assert_in('updated the dataset', response)
        assert_in('<a href="/dataset/{}">Dataset with changed title'
                  .format(dataset['id']),
                  response)

    def test_delete_dataset(self):
        app = self._get_test_app()
        user = factories.User()
        org = factories.Organization()
        dataset = factories.Dataset(owner_org=org['id'], user=user)
        self._clear_activities()
        helpers.call_action(
            'package_delete', context={'user': user['name']}, **dataset)

        url = url_for('organization.activity',
                      id=org['id'])
        response = app.get(url)
        assert_in('<a href="/user/{}">Mr. Test User'.format(user['name']),
                  response)
        assert_in('deleted the dataset', response)
        assert_in('<a href="/dataset/{}">Test Dataset'
                  .format(dataset['id']),
                  response)

    def test_admin_can_see_old_versions(self):
        app = self._get_test_app()
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        dataset = factories.Dataset(user=user)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url, extra_environ=env)
        assert_in('View this version', response)

    def test_public_cant_see_old_versions(self):
        app = self._get_test_app()
        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_not_in('View this version', response)

    def test_admin_can_see_changes(self):
        app = self._get_test_app()
        user = factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        dataset = factories.Dataset()  # activities by system user aren't shown
        dataset['title'] = 'Changed'
        helpers.call_action('package_update', **dataset)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url, extra_environ=env)
        assert_in('Changes', response)
        changes_page = response.click('Changes', extra_environ=env)

    def test_public_cant_see_changes(self):
        app = self._get_test_app()
        dataset = factories.Dataset()  # activities by system user aren't shown
        dataset['title'] = 'Changed'
        helpers.call_action('package_update', **dataset)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_not_in('Changes', response)

    def test_legacy_changed_package_activity(self):
        '''Render an activity that was created with an earlier version of CKAN,
        and it has not been migrated (with migrate_package_activity.py)
        '''
        app = self._get_test_app()

        user = factories.User()
        dataset = factories.Dataset(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = model.Session.query(model.Activity) \
            .filter_by(object_id=dataset['id']) \
            .one()
        revision_id = modern_activity.revision_id
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = 'changed'
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset['id']), context={'model': model})
        activity = model.Activity(
            user_id=user['id'],
            object_id=dataset['id'],
            revision_id=revision_id,
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                'package': dataset_table_dict,
            }
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset['id'],
            object_type=u"Package",
            activity_type=activity_type,
            data={u'package': dataset_table_dict})
        model.Session.add(activity_detail)
        model.Session.flush()

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_in('<a href="/user/{}">Mr. Test User'.format(user['name']),
                  response)
        assert_in('updated the dataset', response)
        assert_in('<a href="/dataset/{}">Test Dataset'.format(dataset['id']),
                  response)

    # ckanext-canada uses their IActivity to add their custom activity to the
    # list of validators: https://github.com/open-data/ckanext-canada/blob/6870e5bc38a04aa8cef191b5e9eb361f9560872b/ckanext/canada/plugins.py#L596
    # but it's easier here to just hack patch it in
    @mock.patch(
        'ckan.logic.validators.object_id_validators', dict(
            object_id_validators.items() +
            [('changed datastore', package_id_exists)])
    )
    def test_custom_activity(self):
        '''Render a custom activity
        '''
        app = self._get_test_app()

        user = factories.User()
        organization = factories.Organization(
            users=[{'name': user['id'], 'capacity': 'admin'}]
        )
        dataset = factories.Dataset(owner_org=organization['id'], user=user)
        resource = factories.Resource(package_id=dataset['id'])
        self._clear_activities()

        # Create a custom Activity object. This one is inspired by:
        # https://github.com/open-data/ckanext-canada/blob/master/ckanext/canada/activity.py
        activity_dict = {
            'user_id': user['id'],
            'object_id': dataset['id'],
            'activity_type': 'changed datastore',
            'data': {
                'resource_id': resource['id'],
                'pkg_type': dataset['type'],
                'resource_name': 'june-2018',
                'owner_org': organization['name'],
                'count': 5,
            }
        }
        helpers.call_action('activity_create', **activity_dict)

        url = url_for('dataset.activity',
                      id=dataset['id'])
        response = app.get(url)
        assert_in('<a href="/user/{}">Mr. Test User'.format(user['name']),
                  response)
        # it renders the activity with fallback.html, since we've not defined
        # changed_datastore.html in this case
        assert_in('changed datastore', response)


class TestChanges(object):  # i.e. the diff
    @classmethod
    def setup_class(cls):
        helpers.reset_db()

    def test_simple(self):
        user = factories.User()
        dataset = factories.Dataset(title='First title', user=user)
        dataset['title'] = 'Second title'
        helpers.call_action('package_update', **dataset)

        app = helpers._get_test_app()
        activity = activity_model.package_activity_list(
            dataset['id'], limit=1, offset=0)[0]
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        response = app.get(url_for('dataset.changes',
                                   id=activity.id),
                           extra_environ=env)
        response.mustcontain('First')
        response.mustcontain('Second')
