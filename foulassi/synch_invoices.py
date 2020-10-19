# Forked and reviewed by Silatchom SIAKA on June 10, Wed 2020
import logging
# sys.path.append("/home/libran/virtualenv/lib/python2.7/site-packages")
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'conf.settings')
import sys

from django.core.files import File

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance, add_database
from ikwen.core.models import Application, Service

from ikwen.core.log import CRONS_LOGGING

from ikwen_foulassi.foulassi.models import ParentProfile, Student, Invoice, Payment


reload(sys)
sys.setdefaultencoding('utf-8')  # Allow system to decode utf-8's strings such as ',",|,?

logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


def synch_invoices():
    f = open("synch_traceback.txt", "a+")
    foulassi = Application.objects.using(UMBRELLA).get(slug='foulassi')
    for school in Service.objects.using(UMBRELLA).filter(app=foulassi):
        print "\n\n---------Processing the school %s-----------------\n\n" % school.project_name
        f.write("\n\n---------Processing the school %s-----------------\n\n" % school.project_name)

        db = school.database
        add_database(db)
        for invoice in Invoice.objects.using(db).all():
            extra_payments = []
            print "Processing invoice %s with amount %d\n" % (invoice.get_title(), invoice.amount)
            f.write("Processing invoice %s with amount %d\n" % (invoice.get_title(), invoice.amount))
            # Store all payments with the same amount and that have the same invoice's id
            queryset = Payment.objects.using(db).filter(invoice=invoice)
            i = 0
            for i in range(queryset.count()):
                first_payment = queryset[i]
                print "First payment No %s of invoice %s with amount %d \n" % (first_payment.id, invoice.get_title(), first_payment.amount)
                f.write("First payment No %s of invoice %s with amount %d \n" % (first_payment.id, invoice.get_title(), first_payment.amount))
                try:
                    second_payment = queryset[i+1]
                    print "Second payment No %s of invoice %s with amount %d  \n" % (second_payment.id, invoice.get_title(), second_payment.amount)
                    f.write("Second payment No %s of invoice %s with amount %d  \n" % (second_payment.id, invoice.get_title(), second_payment.amount))
                except:
                    print "No second payment, we skipped\n"
                    f.write("No second payment, we skipped\n")
                    break
                if first_payment.amount != second_payment.amount:
                    print "Skipped this both payments 'coz no same amount\n"
                    f.write("Skipped this both payments 'coz no same amount\n")
                    continue
                diff = second_payment.created_on - first_payment.created_on
                if diff.seconds <= 5:
                    extra_payments.append(second_payment)

            for payment in extra_payments:
                invoice.paid -= payment.amount
                invoice.save(using=db)
                payment.delete(using=db)
                print "Current invoice amount is now %d\n\n" % invoice.amount
                f.write("Current invoice amount is now %d\n\n" % invoice.amount)
    f.close()


if __name__ == '__main__':
    synch_invoices()