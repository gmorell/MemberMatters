import { Platform } from 'quasar';

export default ({ router, store }) => {
  router.beforeEach((to, from, next) => {
    // if we're in kiosk mode disallow certain pages
    if (Platform.is.electron) {
      if (!to.meta.kiosk) {
        next({ name: 'dashboard' });
      }
    }

    // Check if the user must be logged in to access the route
    if (to.meta.loggedIn === true) {
      if (store.getters['profile/loggedIn'] === true) next();
      else {
        next({ name: 'login' });
      }
    }

    // Check if the user must be an admin to access the route
    if (to.meta.admin === true) {
      if (store.getters['profile/profile'].permissions.admin === true) next();
      else {
        next({ name: 'Error403' });
      }
    }

    // if we are authenticating via SSO then don't update the route
    if (!from.query.sso) {
      next();
    }
  });
};
